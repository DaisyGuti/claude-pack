#!/usr/bin/env python3
"""Inventory a local checkout of a GitHub repository ahead of a move to GitLab.

Read-only. Scans the checkout for GitHub Actions workflows, Dependabot config, CODEOWNERS,
other `.github/` files, git submodules, Git LFS use, and hard-coded GitHub URLs, then prints
a markdown report, JSON, or both.

Usage:
    inventory_github_repo.py PATH [--format markdown|json|both] [--json-out FILE]

Secrets: the report lists secret and variable NAMES only. It never prints a value. Workflow
`env:` and `with:` values are not copied into the output.

YAML: the standard library has no YAML parser, so this file carries a small line-based
reader for the shapes GitHub workflows normally use (block maps, block lists, one-line
flow lists and maps, quoted and plain scalars, `|` and `>` block scalars). Anything else
(anchors, aliases, tags, merge keys, multi-document files, multi-line flow collections,
tabs for indentation) raises an explicit "could not parse" for that file, and the
report says so. Names found by plain text search (secrets, vars, `uses:`) are still
reported for a file that could not be parsed.

Exit codes: 0 report printed, 2 bad input (path missing or not a directory).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

SCHEMA = "gitlab-migration-inventory/1"

# Files above this size are skipped when searching for GitHub URLs. Generated bundles and
# lock files grow past it, and a URL inside them is not something a person edits by hand.
MAX_SCAN_BYTES = 1_000_000

# Cap on individual reference records in the report so the output stays readable. Counts
# per kind stay exact; only the itemised list is cut.
MAX_REFERENCES = 300

# Directories whose contents are not the team's own text. Go `vendor/` and `node_modules/`
# hold thousands of third-party github.com paths that would bury the real findings.
SKIP_DIRS = frozenset(
    {
        ".git",
        "node_modules",
        "vendor",
        ".venv",
        "venv",
        "__pycache__",
        "dist",
        "build",
        "target",
        ".tox",
    }
)

WORKFLOW_SUFFIXES = (".yml", ".yaml")

# Action hints. Key: `uses:` prefix. Value: (kind, what to do in GitLab). `kind` is
# "builtin" (GitLab does it by default), "translate" (a GitLab keyword covers it),
# or "manual" (a person decides). Matched by longest prefix first.
ACTION_HINTS: dict[str, tuple[str, str]] = {
    "actions/checkout": (
        "builtin",
        "GitLab clones the project into CI_PROJECT_DIR before `script` runs. Set GIT_DEPTH, "
        "GIT_STRATEGY or GIT_SUBMODULE_STRATEGY variables if the step used fetch-depth "
        "or submodules.",
    ),
    "actions/setup-": (
        "translate",
        "Pick a job `image:` that carries the toolchain, or install it in `script`.",
    ),
    "actions/cache": ("translate", "Use the `cache:` keyword."),
    "actions/upload-artifact": ("translate", "Use the `artifacts:` keyword."),
    "actions/download-artifact": (
        "translate",
        "Use `needs:` (with artifacts) or `dependencies:` to fetch earlier artifacts.",
    ),
    "actions/github-script": (
        "manual",
        "Rewrite the script against the GitLab API (glab api or curl with a token).",
    ),
    "actions/labeler": ("manual", "No direct equivalent. Use a scheduled job or a triage bot."),
    "actions/stale": ("manual", "No direct equivalent. Use a scheduled job or a triage bot."),
    "docker/login-action": (
        "translate",
        "Run `docker login` with the CI_REGISTRY_* variables in `script`.",
    ),
    "docker/": (
        "translate",
        "Run the docker or buildx CLI in `script`; the ci-harden skill's image build job "
        "is the target.",
    ),
    "google-github-actions/auth": (
        "manual",
        "Replace with `id_tokens:` plus a Security Token Service exchange; "
        "see references/gcp-wif-trust.md.",
    ),
    "google-github-actions/": (
        "translate",
        "Run the gcloud CLI in `script` after the token exchange.",
    ),
    "github/codeql-action": (
        "manual",
        "Pick a replacement scanner (Semgrep CE in a job, or GitLab SAST if the tier has it).",
    ),
    "dependabot/": (
        "manual",
        "Dependabot metadata actions do not apply; see the Renovate section.",
    ),
    "softprops/action-gh-release": ("translate", "Use the `release:` keyword or `glab release`."),
    "ncipollo/release-action": ("translate", "Use the `release:` keyword or `glab release`."),
    "aquasecurity/trivy-action": ("translate", "Run the trivy CLI in `script`."),
    "gitleaks/gitleaks-action": ("translate", "Run the gitleaks CLI in `script`."),
    "peter-evans/": ("manual", "Pull request bots need a GitLab merge request equivalent."),
}

# Runner label prefixes GitHub provides itself. Anything else is a self-hosted or larger
# runner label and needs a GitLab runner with a matching tag.
GITHUB_HOSTED_PREFIXES = ("ubuntu-", "windows-", "macos-")

_KEY_RE = re.compile(
    r"""^(?P<key>"[^"]*"|'[^']*'|[^\s'"\[\]{}#,&*!|>%@`:\-][^:'"\[\]{}#]*?)\s*:(?:\s+(?P<rest>.*))?$"""
)
_BLOCK_SCALAR_RE = re.compile(r"^[|>](?:[+-]\d?|\d[+-]?)?$")


# --------------------------------------------------------------------------- YAML subset


class YamlSubsetError(ValueError):
    """Raised when text uses YAML this reader does not handle. Carries a 1-based line."""

    def __init__(self, line: int, message: str) -> None:
        super().__init__(f"line {line}: {message}")
        self.line = line
        self.message = message


def _strip_comment(text: str) -> str:
    """Cut a trailing `# comment`. A quote only opens a string at the start of a token."""
    quote = ""
    prev = " "
    for index, char in enumerate(text):
        if quote:
            if char == quote:
                quote = ""
        elif char in "\"'" and prev in " \t[{,:":
            quote = char
        elif char == "#" and prev in " \t":
            return text[:index].rstrip()
        prev = char
    return text.rstrip()


def _split_top_level(text: str, lineno: int) -> list[str]:
    """Split a flow collection body on commas that sit outside quotes and brackets."""
    parts: list[str] = []
    depth = 0
    quote = ""
    start = 0
    for index, char in enumerate(text):
        if quote:
            if char == quote:
                quote = ""
        elif char in "\"'":
            quote = char
        elif char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
            if depth < 0:
                raise YamlSubsetError(lineno, "unbalanced bracket in flow collection")
        elif char == "," and depth == 0:
            parts.append(text[start:index].strip())
            start = index + 1
    if quote or depth != 0:
        raise YamlSubsetError(lineno, "unterminated quote or bracket in flow collection")
    tail = text[start:].strip()
    if tail or parts:
        parts.append(tail)
    return [part for part in parts if part != ""]


def _unquote(text: str, lineno: int) -> str:
    if text[0] == '"':
        if len(text) < 2 or not text.endswith('"'):
            raise YamlSubsetError(lineno, "unterminated double-quoted string (multi-line?)")
        return text[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    if len(text) < 2 or not text.endswith("'"):
        raise YamlSubsetError(lineno, "unterminated single-quoted string (multi-line?)")
    return text[1:-1].replace("''", "'")


def _parse_flow_value(text: str, lineno: int) -> Any:
    text = text.strip()
    if text.startswith("["):
        if not text.endswith("]"):
            raise YamlSubsetError(lineno, "multi-line flow list is not supported")
        return [_parse_flow_value(item, lineno) for item in _split_top_level(text[1:-1], lineno)]
    if text.startswith("{"):
        if not text.endswith("}"):
            raise YamlSubsetError(lineno, "multi-line flow map is not supported")
        result: dict[str, Any] = {}
        for item in _split_top_level(text[1:-1], lineno):
            match = _KEY_RE.match(item)
            if not match:
                raise YamlSubsetError(lineno, f"cannot read flow map entry {item!r}")
            key = match.group("key")
            if key[0] in "\"'":
                key = _unquote(key, lineno)
            rest = match.group("rest")
            result[key] = _parse_flow_value(rest, lineno) if rest else None
        return result
    if text[:1] in "\"'":
        return _unquote(text, lineno)
    if text[:1] in "&*!":
        raise YamlSubsetError(lineno, "anchors, aliases and tags are not supported")
    return text


class _Reader:
    def __init__(self, text: str) -> None:
        self.lines = text.splitlines()
        self.i = 0

    # -- line helpers
    def _indent_of(self, raw: str, lineno: int) -> int:
        count = len(raw) - len(raw.lstrip(" "))
        if raw[count : count + 1] == "\t":
            raise YamlSubsetError(lineno, "tab used for indentation")
        return count

    def _skip_blank(self) -> None:
        while self.i < len(self.lines):
            stripped = self.lines[self.i].strip()
            if stripped == "" or stripped.startswith("#"):
                self.i += 1
            else:
                return

    def _current(self) -> tuple[int, str, int] | None:
        """Return (indent, content without comment, 1-based line number) or None at EOF."""
        self._skip_blank()
        if self.i >= len(self.lines):
            return None
        raw = self.lines[self.i]
        lineno = self.i + 1
        indent = self._indent_of(raw, lineno)
        content = _strip_comment(raw[indent:])
        if indent == 0 and content in ("---", "..."):
            raise YamlSubsetError(lineno, "multi-document files are not supported")
        return indent, content, lineno

    # -- grammar
    def parse(self) -> Any:
        self._skip_blank()
        if self.i < len(self.lines) and self.lines[self.i].strip() == "---":
            self.i += 1
        current = self._current()
        if current is None:
            return None
        value = self._block(current[0])
        leftover = self._current()
        if leftover is not None:
            raise YamlSubsetError(leftover[2], "unexpected content after the document")
        return value

    def _block(self, min_indent: int) -> Any:
        current = self._current()
        if current is None or current[0] < min_indent:
            return None
        indent, content, lineno = current
        if content == "-" or content.startswith("- "):
            return self._sequence(indent)
        if _KEY_RE.match(content):
            return self._mapping(indent)
        self.i += 1
        return self._inline(content, indent - 1, lineno)

    def _mapping(self, indent: int) -> dict[str, Any]:
        result: dict[str, Any] = {}
        while True:
            current = self._current()
            if current is None or current[0] < indent:
                return result
            cur_indent, content, lineno = current
            if cur_indent > indent:
                raise YamlSubsetError(lineno, "unexpected indentation")
            if content == "-" or content.startswith("- "):
                return result
            match = _KEY_RE.match(content)
            if not match:
                raise YamlSubsetError(lineno, f"expected 'key: value', found {content[:40]!r}")
            key = match.group("key")
            if key[0] in "\"'":
                key = _unquote(key, lineno)
            if key == "<<":
                raise YamlSubsetError(lineno, "merge keys (<<) are not supported")
            self.i += 1
            rest = match.group("rest") or ""
            if rest == "":
                nxt = self._current()
                if nxt is not None and nxt[0] > indent:
                    result[key] = self._block(nxt[0])
                elif (
                    nxt is not None
                    and nxt[0] == indent
                    and (nxt[1] == "-" or nxt[1].startswith("- "))
                ):
                    result[key] = self._sequence(indent)
                else:
                    result[key] = None
            else:
                result[key] = self._inline(rest, indent, lineno)

    def _sequence(self, indent: int) -> list[Any]:
        items: list[Any] = []
        while True:
            current = self._current()
            if current is None or current[0] < indent:
                return items
            cur_indent, content, lineno = current
            if cur_indent > indent:
                raise YamlSubsetError(lineno, "unexpected indentation")
            if not (content == "-" or content.startswith("- ")):
                return items
            self.i += 1
            after = content[1:]
            stripped = after.lstrip(" ")
            column = indent + 1 + (len(after) - len(stripped))
            if stripped == "":
                nxt = self._current()
                items.append(self._block(nxt[0]) if nxt is not None and nxt[0] > indent else None)
            elif stripped == "-" or stripped.startswith("- "):
                self.i -= 1
                self.lines[self.i] = " " * column + stripped
                items.append(self._sequence(column))
            elif _KEY_RE.match(stripped):
                self.i -= 1
                self.lines[self.i] = " " * column + stripped
                items.append(self._mapping(column))
            else:
                items.append(self._inline(stripped, indent, lineno))

    def _inline(self, rest: str, parent_indent: int, lineno: int) -> Any:
        if rest[0] in "&*!":
            raise YamlSubsetError(lineno, "anchors, aliases and tags are not supported")
        if _BLOCK_SCALAR_RE.match(rest):
            return self._block_scalar(parent_indent)
        if rest[0] in "[{":
            return _parse_flow_value(rest, lineno)
        if rest[0] in "\"'":
            return _unquote(rest, lineno)
        return rest

    def _block_scalar(self, parent_indent: int) -> str:
        collected: list[str] = []
        base: int | None = None
        while self.i < len(self.lines):
            raw = self.lines[self.i]
            if raw.strip() == "":
                collected.append("")
                self.i += 1
                continue
            indent = len(raw) - len(raw.lstrip(" "))
            if indent <= parent_indent:
                break
            if base is None:
                base = indent
            collected.append(raw[base:] if indent >= base else raw.lstrip())
            self.i += 1
        return "\n".join(collected).rstrip("\n")


def parse_yaml_subset(text: str) -> Any:
    """Parse the YAML subset described in the module docstring or raise YamlSubsetError."""
    return _Reader(text).parse()


# ------------------------------------------------------------------------ workflow analysis

_SECRET_RE = re.compile(r"\bsecrets\.([A-Za-z_][A-Za-z0-9_]*)")
_SECRET_INDEX_RE = re.compile(r"\bsecrets\[\s*['\"]([^'\"]+)['\"]\s*\]")
_SECRET_DYNAMIC_RE = re.compile(r"\bsecrets\[\s*[^'\"\s]")
_VAR_RE = re.compile(r"\bvars\.([A-Za-z_][A-Za-z0-9_]*)")
_CONTEXT_RE = re.compile(r"\bgithub\.([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?)")
_USES_RE = re.compile(r"^\s*(?:-\s+)?uses:\s*['\"]?([^\s'\"#]+)")
_GH_CLI_RE = re.compile(r"(?<![\w-])gh\s+(?:pr|issue|release|api|run|workflow|repo|label)\b")
_INHERIT_RE = re.compile(r"^\s*secrets:\s*inherit\b", re.MULTILINE)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _hint_for(ref: str) -> tuple[str, str]:
    if ref.startswith("./"):
        return (
            "manual",
            "Local action: move its steps into a hidden job (`.name`) with `extends`, "
            "an `include:`, or a CI/CD component.",
        )
    if ref.startswith("docker://"):
        return "translate", "Use the container as the job `image:`."
    best = ""
    for prefix in ACTION_HINTS:
        if ref.startswith(prefix) and len(prefix) > len(best):
            best = prefix
    if best:
        return ACTION_HINTS[best]
    return (
        "manual",
        "Third-party action: run the tool's CLI in `script`, or find an include or component.",
    )


def _trigger_records(on_value: Any) -> list[dict[str, Any]]:
    """Normalise the `on:` key (string, list or map) to a list of trigger records."""
    records: list[dict[str, Any]] = []
    if isinstance(on_value, str):
        return [{"event": on_value}]
    if isinstance(on_value, list):
        return [{"event": str(item)} for item in on_value]
    if isinstance(on_value, dict):
        for event, detail in on_value.items():
            record: dict[str, Any] = {"event": event}
            if isinstance(detail, dict):
                for key in ("branches", "branches-ignore", "tags", "paths", "types"):
                    if key in detail:
                        record[key] = [str(x) for x in _as_list(detail[key])]
                if event in ("workflow_dispatch", "workflow_call") and "inputs" in detail:
                    inputs = detail["inputs"]
                    record["inputs"] = sorted(inputs) if isinstance(inputs, dict) else []
            elif isinstance(detail, list) and event == "schedule":
                record["crons"] = [
                    str(item.get("cron"))
                    for item in detail
                    if isinstance(item, dict) and "cron" in item
                ]
            elif isinstance(detail, list):
                record["branches"] = [str(x) for x in detail]
            records.append(record)
    return records


def _permissions_summary(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): str(v) for k, v in value.items()}
    if isinstance(value, str):
        return value
    return None


def _id_token_write(permissions: Any) -> bool:
    return isinstance(permissions, dict) and str(permissions.get("id-token", "")) == "write"


def _runs_on_labels(value: Any) -> list[str]:
    if isinstance(value, dict):
        out = []
        for key in ("group", "labels"):
            for item in _as_list(value.get(key)):
                out.append(f"{key}:{item}")
        return out
    return [str(item) for item in _as_list(value)]


def _is_self_hosted(labels: list[str]) -> bool:
    for label in labels:
        if label.startswith("${{"):
            continue
        if label == "self-hosted" or label.startswith(("group:", "labels:")):
            return True
        if not label.startswith(GITHUB_HOSTED_PREFIXES):
            return True
    return False


def _flag(flag_id: str, severity: str, where: str, message: str) -> dict[str, str]:
    return {"id": flag_id, "severity": severity, "where": where, "message": message}


def analyze_workflow(rel_path: str, text: str) -> dict[str, Any]:
    """Return a record for one workflow file. Never raises on bad YAML."""
    record: dict[str, Any] = {"file": rel_path, "parsed": False, "parse_error": None}
    flags: list[dict[str, str]] = []

    secrets = set(_SECRET_RE.findall(text)) | set(_SECRET_INDEX_RE.findall(text))
    record["secrets"] = sorted(secrets - {"GITHUB_TOKEN"})
    record["uses_github_token"] = "GITHUB_TOKEN" in secrets or "github.token" in text
    record["vars"] = sorted(set(_VAR_RE.findall(text)))
    record["github_contexts"] = sorted(set(_CONTEXT_RE.findall(text)))
    record["secrets_inherit"] = bool(_INHERIT_RE.search(text))
    if _SECRET_DYNAMIC_RE.search(text):
        flags.append(
            _flag(
                "dynamic-secret-name",
                "manual",
                rel_path,
                "A secret is looked up by a computed name; list its possible names by hand.",
            )
        )
    uses_refs = sorted({m.group(1) for line in text.splitlines() if (m := _USES_RE.match(line))})
    record["uses"] = uses_refs
    if _GH_CLI_RE.search(text):
        record["gh_cli"] = True
        flags.append(
            _flag(
                "gh-cli",
                "manual",
                rel_path,
                "A step calls the gh CLI; the GitLab job needs glab or the API instead.",
            )
        )

    try:
        doc = parse_yaml_subset(text)
    except YamlSubsetError as err:
        record["parse_error"] = str(err)
        flags.append(
            _flag(
                "parse-failed",
                "manual",
                rel_path,
                f"Could not parse this workflow ({err}). Read it by hand; names found by text "
                "search are still listed.",
            )
        )
        record["flags"] = flags
        return record
    if not isinstance(doc, dict):
        record["parse_error"] = "top level is not a mapping"
        flags.append(_flag("parse-failed", "manual", rel_path, "Top level is not a mapping."))
        record["flags"] = flags
        return record

    record["parsed"] = True
    record["name"] = str(doc["name"]) if isinstance(doc.get("name"), str) else None
    triggers = _trigger_records(doc.get("on"))
    record["triggers"] = triggers
    events = {t["event"] for t in triggers}
    record["permissions"] = _permissions_summary(doc.get("permissions"))
    record["env_names"] = sorted(doc["env"]) if isinstance(doc.get("env"), dict) else []
    record["concurrency"] = doc.get("concurrency") is not None

    if "pull_request_target" in events:
        flags.append(
            _flag(
                "pull-request-target",
                "manual",
                rel_path,
                "pull_request_target runs with base-repository secrets. GitLab has no direct "
                "equivalent; decide how fork merge requests are handled.",
            )
        )
    if "workflow_run" in events:
        flags.append(
            _flag(
                "workflow-run",
                "manual",
                rel_path,
                "workflow_run chains workflows. Use parent-child or multi-project pipelines.",
            )
        )
    if "workflow_call" in events:
        flags.append(
            _flag(
                "workflow-call-definition",
                "review",
                rel_path,
                "This file is a reusable workflow. "
                "Translate it to an include file or a CI/CD component.",
            )
        )
    if "schedule" in events:
        flags.append(
            _flag(
                "schedule-trigger",
                "review",
                rel_path,
                "Schedules live outside .gitlab-ci.yml. Create pipeline schedules after the move.",
            )
        )
    if "workflow_dispatch" in events:
        flags.append(
            _flag(
                "workflow-dispatch",
                "info",
                rel_path,
                "workflow_dispatch becomes a manual pipeline run (web source) "
                "with prefilled variables.",
            )
        )
    if record["concurrency"]:
        flags.append(
            _flag(
                "concurrency",
                "review",
                rel_path,
                "Workflow-level concurrency maps to workflow:auto_cancel, "
                "interruptible or resource_group.",
            )
        )

    jobs_raw = doc.get("jobs")
    jobs: list[dict[str, Any]] = []
    if not isinstance(jobs_raw, dict):
        flags.append(_flag("parse-failed", "manual", rel_path, "No `jobs:` mapping was found."))
        jobs_raw = {}
    wif = _id_token_write(doc.get("permissions"))
    for job_id, job in jobs_raw.items():
        if not isinstance(job, dict):
            flags.append(
                _flag("parse-failed", "manual", f"{rel_path}:{job_id}", "Job is not a mapping.")
            )
            continue
        labels = _runs_on_labels(job.get("runs-on"))
        permissions = _permissions_summary(job.get("permissions"))
        job_oidc = _id_token_write(job.get("permissions"))
        wif = wif or job_oidc
        strategy = job.get("strategy") if isinstance(job.get("strategy"), dict) else {}
        matrix = strategy.get("matrix") if isinstance(strategy.get("matrix"), dict) else {}
        services = job.get("services") if isinstance(job.get("services"), dict) else {}
        environment = job.get("environment")
        if isinstance(environment, dict):
            environment = environment.get("name")
        container = job.get("container")
        if isinstance(container, dict):
            container = container.get("image")
        steps = job.get("steps") if isinstance(job.get("steps"), list) else []
        step_uses = sorted(
            {
                str(s["uses"])
                for s in steps
                if isinstance(s, dict) and isinstance(s.get("uses"), str)
            }
        )
        auth_keys: list[str] = []
        for step in steps:
            if (
                isinstance(step, dict)
                and isinstance(step.get("uses"), str)
                and step["uses"].startswith("google-github-actions/auth")
                and isinstance(step.get("with"), dict)
            ):
                auth_keys = sorted(step["with"])
        job_record = {
            "id": str(job_id),
            "runs_on": labels,
            "self_hosted": _is_self_hosted(labels) if labels else False,
            "needs": [str(n) for n in _as_list(job.get("needs"))],
            "environment": str(environment) if environment else None,
            "permissions": permissions,
            "id_token_write": job_oidc,
            "reusable_workflow": str(job["uses"]) if isinstance(job.get("uses"), str) else None,
            "matrix_axes": sorted(k for k in matrix if k not in ("include", "exclude")),
            "matrix_include_exclude": sorted(k for k in matrix if k in ("include", "exclude")),
            "services": sorted(services),
            "container": str(container) if container else None,
            "step_uses": step_uses,
            "google_auth_with_keys": auth_keys,
            "has_if": "if" in job,
        }
        jobs.append(job_record)
        where = f"{rel_path}:{job_id}"
        if job_record["self_hosted"]:
            flags.append(
                _flag(
                    "self-hosted-runner",
                    "review",
                    where,
                    f"Runner labels {labels} need GitLab runners with matching tags.",
                )
            )
        if job_record["matrix_include_exclude"]:
            flags.append(
                _flag(
                    "matrix-include-exclude",
                    "manual",
                    where,
                    "Matrix include/exclude has no keyword in parallel:matrix; "
                    "write the combinations out.",
                )
            )
        if job_record["reusable_workflow"]:
            flags.append(
                _flag(
                    "reusable-workflow-call",
                    "manual",
                    where,
                    f"Calls reusable workflow {job_record['reusable_workflow']}; "
                    "translate it first.",
                )
            )
        if job_record["environment"]:
            flags.append(
                _flag(
                    "environment-deployment",
                    "review",
                    where,
                    f"Deploys to environment {job_record['environment']!r}; recreate it in GitLab "
                    "and check its protection and approval settings.",
                )
            )
        if job_oidc:
            flags.append(
                _flag(
                    "oidc-id-token",
                    "manual",
                    where,
                    "Job requests an OIDC token (id-token: write); "
                    "see references/gcp-wif-trust.md.",
                )
            )
        if job_record["services"]:
            flags.append(
                _flag(
                    "services",
                    "info",
                    where,
                    "Service containers map to the `services:` keyword.",
                )
            )
    if wif:
        record["id_token_write"] = True
        if not any(f["id"] == "oidc-id-token" for f in flags):
            flags.append(
                _flag(
                    "oidc-id-token",
                    "manual",
                    rel_path,
                    "Workflow requests an OIDC token (id-token: write); "
                    "see references/gcp-wif-trust.md.",
                )
            )
    else:
        record["id_token_write"] = False

    for ref in uses_refs:
        kind, hint = _hint_for(ref)
        if kind == "manual" and ref.startswith("./"):
            flags.append(_flag("local-action", "manual", rel_path, f"{ref}: {hint}"))
        elif kind == "manual" and ref.startswith("actions/github-script"):
            flags.append(_flag("github-script", "manual", rel_path, hint))
        elif kind == "manual" and not ref.startswith(
            ("google-github-actions/auth", "github/codeql", "dependabot/", "actions/")
        ):
            flags.append(_flag("third-party-action", "manual", rel_path, f"{ref}: {hint}"))

    record["jobs"] = jobs
    record["flags"] = flags
    return record


# ------------------------------------------------------------------ other repository files


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _strip_credentials(url: str) -> str:
    return re.sub(r"(://)[^/@\s]+@", r"\1", url)


def read_origin(root: Path) -> dict[str, Any]:
    """Read the origin URL from .git/config by text search. Credentials are removed."""
    config = root / ".git" / "config"
    text = _read_text(config) if config.is_file() else None
    if not text:
        return {"url": None, "owner_repo": None}
    match = re.search(r'\[remote "origin"\][^\[]*?url\s*=\s*(\S+)', text)
    if not match:
        return {"url": None, "owner_repo": None}
    url = _strip_credentials(match.group(1))
    repo = re.search(r"github\.com[/:]([\w.\-]+)/([\w.\-]+?)(?:\.git)?/?$", url)
    return {"url": url, "owner_repo": f"{repo.group(1)}/{repo.group(2)}" if repo else None}


def analyze_dependabot(root: Path) -> dict[str, Any] | None:
    for name in ("dependabot.yml", "dependabot.yaml"):
        path = root / ".github" / name
        if not path.is_file():
            continue
        rel = f".github/{name}"
        text = _read_text(path) or ""
        record: dict[str, Any] = {"file": rel, "parsed": False, "parse_error": None, "updates": []}
        try:
            doc = parse_yaml_subset(text)
        except YamlSubsetError as err:
            record["parse_error"] = str(err)
            return record
        if not isinstance(doc, dict):
            record["parse_error"] = "top level is not a mapping"
            return record
        record["parsed"] = True
        record["registries_configured"] = isinstance(doc.get("registries"), dict)
        for item in _as_list(doc.get("updates")):
            if not isinstance(item, dict):
                continue
            schedule = item.get("schedule") if isinstance(item.get("schedule"), dict) else {}
            extras = sorted(
                k
                for k in item
                if k
                not in (
                    "package-ecosystem",
                    "directory",
                    "directories",
                    "schedule",
                )
            )
            record["updates"].append(
                {
                    "ecosystem": str(item.get("package-ecosystem", "")),
                    "directories": [
                        str(d) for d in _as_list(item.get("directories") or item.get("directory"))
                    ],
                    "interval": str(schedule.get("interval", "")),
                    "extra_settings": extras,
                }
            )
        return record
    return None


def analyze_codeowners(root: Path) -> dict[str, Any]:
    found: list[str] = []
    for rel in (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS", ".gitlab/CODEOWNERS"):
        if (root / rel).is_file():
            found.append(rel)
    record: dict[str, Any] = {
        "found": found,
        "github_location": next((f for f in found if f != ".gitlab/CODEOWNERS"), None),
        "gitlab_ready": any(
            f in ("CODEOWNERS", "docs/CODEOWNERS", ".gitlab/CODEOWNERS") for f in found
        ),
        "rules": 0,
        "inline_comments": 0,
        "owners": [],
        "team_owners": [],
    }
    if not found:
        return record
    text = _read_text(root / found[0]) or ""
    owners: set[str] = set()
    rules = 0
    inline_comments = 0
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        line = _strip_comment(stripped)
        if line != stripped:
            inline_comments += 1
        rules += 1
        for token in line.split()[1:]:
            if token.startswith("@") or re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", token):
                owners.add(token)
    record["inline_comments"] = inline_comments
    record["rules"] = rules
    record["owners"] = sorted(owners)
    record["team_owners"] = sorted(o for o in owners if o.startswith("@") and "/" in o)
    return record


_EXTRAS: list[tuple[str, str, str]] = [
    (
        ".github/ISSUE_TEMPLATE",
        "dir",
        ".gitlab/issue_templates/ (check how YAML issue forms translate)",
    ),
    (".github/PULL_REQUEST_TEMPLATE.md", "file", ".gitlab/merge_request_templates/"),
    (".github/PULL_REQUEST_TEMPLATE", "dir", ".gitlab/merge_request_templates/"),
    (
        ".github/FUNDING.yml",
        "file",
        "No GitLab equivalent; drop it or move the links into the README.",
    ),
    (".github/SECURITY.md", "file", "SECURITY.md in the repository root or docs/."),
    (".github/CODE_OF_CONDUCT.md", "file", "CODE_OF_CONDUCT.md in the repository root."),
    (".github/CONTRIBUTING.md", "file", "CONTRIBUTING.md in the repository root."),
    (
        ".github/release.yml",
        "file",
        "No GitLab equivalent; release notes come from the release keyword or changelog tooling.",
    ),
    (
        ".github/labeler.yml",
        "file",
        "Config for a GitHub labeler action; replace with a scheduled job or drop it.",
    ),
    (
        ".github/stale.yml",
        "file",
        "Config for a GitHub stale bot; replace with a scheduled job or drop it.",
    ),
    (
        ".github/settings.yml",
        "file",
        "Config for a GitHub App (repository settings bot); recreate the settings in GitLab.",
    ),
    (
        ".github/actions",
        "dir",
        "Local composite actions; convert to hidden jobs, includes or components.",
    ),
    (
        ".github/copilot-instructions.md",
        "file",
        "GitHub Copilot instructions; move them to the tool the team uses next.",
    ),
    ("SECURITY.md", "file", "Keep in place; GitLab reads it from the repository root."),
]


def collect_extras(root: Path) -> list[dict[str, str]]:
    out = []
    for rel, kind, target in _EXTRAS:
        path = root / rel
        present = path.is_dir() if kind == "dir" else path.is_file()
        if present:
            out.append({"path": rel, "gitlab_destination": target})
    return out


def analyze_submodules(root: Path) -> list[dict[str, Any]]:
    path = root / ".gitmodules"
    text = _read_text(path) if path.is_file() else None
    if not text:
        return []
    modules: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw in text.splitlines():
        line = raw.strip()
        header = re.match(r'\[submodule\s+"(.+)"\]', line)
        if header:
            current = {"name": header.group(1), "path": None, "url": None}
            modules.append(current)
            continue
        if current is None or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key in ("path", "url"):
            current[key] = _strip_credentials(value.strip())
    for module in modules:
        url = module.get("url") or ""
        module["relative"] = url.startswith(("./", "../"))
        module["github"] = "github.com" in url
    return modules


def analyze_lfs(root: Path) -> dict[str, Any]:
    patterns: list[str] = []
    attributes = root / ".gitattributes"
    text = _read_text(attributes) if attributes.is_file() else None
    for line in (text or "").splitlines():
        if "filter=lfs" in line:
            patterns.append(line.split()[0])
    lfsconfig = root / ".lfsconfig"
    url = None
    if lfsconfig.is_file():
        match = re.search(r"url\s*=\s*(\S+)", _read_text(lfsconfig) or "")
        url = _strip_credentials(match.group(1)) if match else None
    return {
        "used": bool(patterns),
        "patterns": patterns,
        "lfsconfig_present": lfsconfig.is_file(),
        "lfsconfig_url": url,
    }


# --------------------------------------------------------------------- reference scanning

_REFERENCE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "workflow-badge",
        re.compile(r"github\.com/([\w.\-]+)/([\w.\-]+)/actions/workflows/[^\s)\"']+/badge\.svg"),
    ),
    ("ghcr", re.compile(r"ghcr\.io/([\w.\-]+)/([\w.\-/]+)")),
    ("github-packages", re.compile(r"\b(?:npm|maven|nuget|rubygems)\.pkg\.github\.com")),
    ("github-pages", re.compile(r"\b([\w\-]+)\.github\.io\b")),
    ("raw-content", re.compile(r"raw\.githubusercontent\.com/([\w.\-]+)/([\w.\-]+)")),
    ("github-api", re.compile(r"\bapi\.github\.com\b")),
    ("github-url", re.compile(r"(?<![\w.])github\.com[/:]([\w.\-]+)/([\w.\-]+)")),
]

_MANIFEST_NAMES = {
    "package.json",
    "go.mod",
    "go.sum",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "requirements.txt",
    "Cargo.toml",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "Gemfile",
    "composer.json",
}


def _category(rel: str) -> str:
    name = rel.rsplit("/", 1)[-1]
    if rel.startswith(".github/workflows/"):
        return "workflow"
    if name in _MANIFEST_NAMES:
        return "package-manifest"
    if name == ".gitmodules":
        return "submodule"
    if name.lower().startswith(("readme", "changelog", "contributing")) or rel.startswith("docs/"):
        return "docs"
    return "other"


def _iter_text_files(root: Path) -> list[Path]:
    """List regular files under root in a stable order, pruning SKIP_DIRS without descending."""
    files: list[Path] = []
    for current, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(names):
            path = Path(current) / name
            if not path.is_symlink() and path.is_file():
                files.append(path)
    return files


def scan_references(root: Path, own_repo: str | None) -> dict[str, Any]:
    counts: dict[str, int] = {}
    items: list[dict[str, Any]] = []
    other_links = 0
    omitted = 0
    go_module: str | None = None
    skipped_large = 0
    for path in _iter_text_files(root):
        rel = path.relative_to(root).as_posix()
        try:
            if path.stat().st_size > MAX_SCAN_BYTES:
                skipped_large += 1
                continue
            data = path.read_bytes()
        except OSError:
            continue
        if b"\0" in data[:4096]:
            continue
        text = data.decode("utf-8", errors="replace")
        if path.name == "go.mod":
            module = re.search(r"^module\s+(github\.com/\S+)", text, re.MULTILINE)
            if module:
                go_module = module.group(1)
        for lineno, line in enumerate(text.splitlines(), start=1):
            if "github" not in line and "ghcr.io" not in line:
                continue
            taken: list[tuple[int, int]] = []
            for kind, pattern in _REFERENCE_PATTERNS:
                for match in pattern.finditer(line):
                    span = match.span()
                    if any(span[0] < end and start < span[1] for start, end in taken):
                        continue
                    taken.append(span)
                    counts[kind] = counts.get(kind, 0) + 1
                    own: bool | None = None
                    if kind in ("github-url", "workflow-badge") and own_repo:
                        found = f"{match.group(1)}/{match.group(2)}".removesuffix(".git").lower()
                        own = found == own_repo.lower()
                    if own is False:
                        other_links += 1
                        continue
                    if len(items) >= MAX_REFERENCES:
                        omitted += 1
                        continue
                    items.append(
                        {
                            "file": rel,
                            "line": lineno,
                            "kind": kind,
                            "text": match.group(0),
                            "category": _category(rel),
                            "own_repo": own,
                        }
                    )
    return {
        "counts": dict(sorted(counts.items())),
        "items": items,
        "truncated": omitted > 0,
        "other_github_links_not_listed": other_links,
        "go_module": go_module,
        "files_skipped_for_size": skipped_large,
        "skipped_dirs": sorted(SKIP_DIRS),
    }


# ---------------------------------------------------------------------------- orchestration


def build_inventory(root: Path) -> dict[str, Any]:
    origin = read_origin(root)
    workflows: list[dict[str, Any]] = []
    wf_dir = root / ".github" / "workflows"
    if wf_dir.is_dir():
        for path in sorted(wf_dir.iterdir()):
            if path.is_file() and path.suffix in WORKFLOW_SUFFIXES:
                text = _read_text(path)
                rel = path.relative_to(root).as_posix()
                if text is None:
                    workflows.append(
                        {
                            "file": rel,
                            "parsed": False,
                            "parse_error": "file could not be read",
                            "secrets": [],
                            "vars": [],
                            "uses": [],
                            "flags": [
                                _flag("parse-failed", "manual", rel, "File could not be read.")
                            ],
                        }
                    )
                    continue
                workflows.append(analyze_workflow(rel, text))

    dependabot = analyze_dependabot(root)
    codeowners = analyze_codeowners(root)
    extras = collect_extras(root)
    submodules = analyze_submodules(root)
    lfs = analyze_lfs(root)
    references = scan_references(root, origin["owner_repo"])

    secret_names = sorted({s for w in workflows for s in w.get("secrets", [])})
    var_names = sorted({v for w in workflows for v in w.get("vars", [])})
    environments = sorted(
        {j["environment"] for w in workflows for j in w.get("jobs", []) if j.get("environment")}
    )
    actions: dict[str, dict[str, Any]] = {}
    for workflow in workflows:
        for ref in workflow.get("uses", []):
            kind, hint = _hint_for(ref)
            entry = actions.setdefault(ref, {"ref": ref, "kind": kind, "hint": hint, "files": []})
            entry["files"].append(workflow["file"])
    flags = [f for w in workflows for f in w.get("flags", [])]
    if codeowners["found"] and not codeowners["gitlab_ready"]:
        flags.append(
            _flag(
                "codeowners-location",
                "review",
                codeowners["found"][0],
                "GitLab reads CODEOWNERS from the root, docs/ or .gitlab/ only; move the file.",
            )
        )
    if codeowners["team_owners"]:
        flags.append(
            _flag(
                "codeowners-teams",
                "manual",
                codeowners["found"][0],
                "Owners written as @org/team must become GitLab users or groups.",
            )
        )
    if codeowners["inline_comments"]:
        flags.append(
            _flag(
                "codeowners-inline-comments",
                "manual",
                codeowners["found"][0],
                "GitLab does not support inline comments in CODEOWNERS, and owners named in a "
                "comment are still parsed. Move each comment to its own line.",
            )
        )
    if dependabot:
        flags.append(
            _flag(
                "dependabot",
                "manual",
                dependabot["file"],
                "Dependabot has no GitLab version; choose Renovate or a scanner in CI.",
            )
        )
    if lfs["used"]:
        flags.append(
            _flag(
                "lfs",
                "review",
                ".gitattributes",
                "Git LFS is in use; confirm the importer fetched the objects.",
            )
        )
    if any(m["github"] for m in submodules):
        flags.append(
            _flag(
                "submodules-github",
                "review",
                ".gitmodules",
                "Submodule URLs point at github.com; repoint any that move.",
            )
        )
    if references["counts"].get("ghcr") or references["counts"].get("github-packages"):
        flags.append(
            _flag(
                "registry-references",
                "review",
                "repository",
                "Images or packages are pulled from GitHub registries; plan the registry move.",
            )
        )
    if references["go_module"]:
        flags.append(
            _flag(
                "go-module-path",
                "manual",
                "go.mod",
                f"Go module path {references['go_module']} names GitHub; "
                "changing it edits every import.",
            )
        )
    wif_used = any(w.get("id_token_write") for w in workflows) or any(
        j.get("google_auth_with_keys") for w in workflows for j in w.get("jobs", [])
    )

    return {
        "schema": SCHEMA,
        "root": root.name,
        "origin": origin,
        "workflows": workflows,
        "actions_used": sorted(actions.values(), key=lambda a: a["ref"]),
        "secret_names": secret_names,
        "variable_names": var_names,
        "environments": environments,
        "uses_github_token": any(w.get("uses_github_token") for w in workflows),
        "gcp_workload_identity": wif_used,
        "dependabot": dependabot,
        "codeowners": codeowners,
        "github_extras": extras,
        "submodules": submodules,
        "lfs": lfs,
        "references": references,
        "flags": flags,
        "has_github_dir": (root / ".github").is_dir(),
    }


# --------------------------------------------------------------------------------- markdown


def _cell(value: Any) -> str:
    text = ", ".join(str(v) for v in value) if isinstance(value, list) else str(value or "")
    return text.replace("|", "\\|") or "-"


def _names(values: list[str], empty: str = "none found") -> str:
    return ", ".join(f"`{v}`" for v in values) or empty


def render_markdown(inv: dict[str, Any]) -> str:
    out: list[str] = ["# GitHub repository inventory", ""]
    origin = inv["origin"]
    out.append(f"- Checkout: `{inv['root']}`")
    out.append(
        f"- Origin remote: `{origin['url']}`"
        if origin["url"]
        else "- Origin remote: not found in .git/config"
    )
    out.append("- Secret and variable VALUES are never read into this report; names only.")
    if not inv["has_github_dir"]:
        out.append(
            "- No `.github/` directory found. "
            "If this is the wrong folder, rerun with the repo root."
        )
    out.append("")

    out += ["## Workflows", ""]
    if inv["workflows"]:
        out.append("| File | Triggers | Jobs | Runners | Secrets | Parsed |")
        out.append("|---|---|---|---|---|---|")
        for w in inv["workflows"]:
            triggers = [t["event"] for t in w.get("triggers", [])]
            jobs = [j["id"] for j in w.get("jobs", [])]
            runners = sorted({label for j in w.get("jobs", []) for label in j["runs_on"]})
            parsed = "yes" if w["parsed"] else f"NO: {w['parse_error']}"
            out.append(
                f"| `{w['file']}` | {_cell(triggers)} | {_cell(jobs)} | {_cell(runners)} "
                f"| {_cell(w.get('secrets'))} | {_cell(parsed)} |"
            )
    else:
        out.append("No workflow files found under `.github/workflows/`.")
    out.append("")

    out += ["## Secrets and variables (names only)", ""]
    out.append(f"- Secrets: {_names(inv['secret_names'])}")
    out.append(f"- Variables (vars.*): {_names(inv['variable_names'])}")
    out.append(f"- Environments: {_names(inv['environments'])}")
    token = "yes (becomes CI_JOB_TOKEN or a scoped token)" if inv["uses_github_token"] else "no"
    out.append(f"- Uses GITHUB_TOKEN: {token}")
    wif = (
        "likely in use (id-token: write or google-github-actions/auth)"
        if inv["gcp_workload_identity"]
        else "not detected"
    )
    out.append(f"- Google Cloud workload identity: {wif}")
    out.append("")

    out += ["## Actions used", ""]
    if inv["actions_used"]:
        out.append("| Action | Kind | In GitLab |")
        out.append("|---|---|---|")
        for a in inv["actions_used"]:
            out.append(f"| `{a['ref']}` | {a['kind']} | {_cell(a['hint'])} |")
    else:
        out.append("None.")
    out.append("")

    out += ["## Needs a person (manual translation or a decision)", ""]
    manual = [f for f in inv["flags"] if f["severity"] == "manual"]
    review = [f for f in inv["flags"] if f["severity"] == "review"]
    for title, group in (("Manual", manual), ("Review", review)):
        out.append(f"### {title}")
        out.append("")
        if group:
            for f in group:
                out.append(f"- `{f['id']}` at `{f['where']}`: {f['message']}")
        else:
            out.append("None.")
        out.append("")

    out += ["## Dependabot", ""]
    dep = inv["dependabot"]
    if dep is None:
        out.append("No Dependabot configuration found.")
    elif not dep["parsed"]:
        out.append(f"`{dep['file']}` could not be parsed: {dep['parse_error']}. Read it by hand.")
    else:
        for u in dep["updates"]:
            extra = f" (also sets: {', '.join(u['extra_settings'])})" if u["extra_settings"] else ""
            interval = u["interval"] or "no interval"
            out.append(f"- `{u['ecosystem']}` in {_cell(u['directories'])}, {interval}{extra}")
        if dep.get("registries_configured"):
            out.append("- Private registries are configured; Renovate needs matching host rules.")
    out.append("")

    out += ["## CODEOWNERS", ""]
    co = inv["codeowners"]
    if not co["found"]:
        out.append("No CODEOWNERS file found.")
    else:
        out.append(f"- Found at: {', '.join(f'`{f}`' for f in co['found'])}")
        out.append(f"- Rules: {co['rules']}")
        out.append(f"- Owners: {', '.join(f'`{o}`' for o in co['owners']) or 'none'}")
        if co["team_owners"]:
            out.append(f"- Team owners to remap: {', '.join(f'`{o}`' for o in co['team_owners'])}")
        if not co["gitlab_ready"]:
            out.append("- Location: GitLab does not read `.github/CODEOWNERS`; move it.")
    out.append("")

    out += ["## Other .github files", ""]
    if inv["github_extras"]:
        for e in inv["github_extras"]:
            out.append(f"- `{e['path']}` -> {e['gitlab_destination']}")
    else:
        out.append("None found.")
    out.append("")

    out += ["## Submodules and LFS", ""]
    if inv["submodules"]:
        for m in inv["submodules"]:
            note = (
                "relative URL"
                if m["relative"]
                else ("github.com URL" if m["github"] else "other host")
            )
            out.append(f"- `{m['path']}` -> `{m['url']}` ({note})")
    else:
        out.append("- No submodules.")
    lfs = inv["lfs"]
    out.append(
        f"- Git LFS: {'in use for ' + _names(lfs['patterns']) if lfs['used'] else 'not used'}"
    )
    if lfs["lfsconfig_present"]:
        out.append(
            f"- `.lfsconfig` present (url: `{lfs['lfsconfig_url']}`); "
            "a different host stops LFS download in the importer."
        )
    out.append("")

    out += ["## Hard-coded GitHub references", ""]
    refs = inv["references"]
    if refs["counts"]:
        out.append("Counts by kind: " + ", ".join(f"{k}={v}" for k, v in refs["counts"].items()))
        if refs["other_github_links_not_listed"]:
            out.append(
                f"- {refs['other_github_links_not_listed']} github.com links point at "
                "other projects and are not listed."
            )
        for i in refs["items"]:
            tag = {True: "this repo", False: "other", None: "-"}[i["own_repo"]]
            out.append(
                f"- `{i['file']}:{i['line']}` [{i['kind']}, {i['category']}, {tag}] `{i['text']}`"
            )
        if refs["truncated"]:
            out.append("- List cut off; counts above are complete.")
    else:
        out.append("None found.")
    if refs["files_skipped_for_size"]:
        out.append(
            f"- {refs['files_skipped_for_size']} file(s) over the size limit were not scanned."
        )
    out.append(f"- Directories skipped: {', '.join(refs['skipped_dirs'])}")
    out.append("")
    return "\n".join(out)


# ------------------------------------------------------------------------------------ CLI


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inventory a local GitHub checkout before a GitLab migration (read-only)."
    )
    parser.add_argument("path", help="root of a local checkout of the GitHub repository")
    parser.add_argument(
        "--format",
        choices=("markdown", "json", "both"),
        default="markdown",
        help="what to print to stdout (default: markdown)",
    )
    parser.add_argument("--json-out", metavar="FILE", help="also write the JSON inventory to FILE")
    args = parser.parse_args(argv)

    root = Path(args.path)
    if not root.is_dir():
        print(
            f"inventory_github_repo.py: {args.path!r} is not a directory. "
            "Pass the root of a local checkout of the GitHub repository.",
            file=sys.stderr,
        )
        return 2

    inventory = build_inventory(root.resolve())
    if args.json_out:
        try:
            Path(args.json_out).write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
        except OSError as err:
            print(
                f"inventory_github_repo.py: cannot write {args.json_out!r}: {err}. "
                "Choose a writable path for --json-out.",
                file=sys.stderr,
            )
            return 2
    if args.format in ("markdown", "both"):
        print(render_markdown(inventory))
    if args.format == "both":
        print("\n<!-- JSON inventory follows -->\n")
    if args.format in ("json", "both"):
        print(json.dumps(inventory, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
