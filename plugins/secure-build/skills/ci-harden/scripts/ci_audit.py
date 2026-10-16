#!/usr/bin/env python3
"""Audit GitHub Actions workflows and GitLab CI files for the obvious hardening gaps.

Usage:
    ci_audit.py [--json] [--fail-on info|warning|error] PATH [PATH ...]

PATH is a workflow file, a .gitlab-ci.yml file or a directory. In a directory the script
reads .github/workflows/*.yml|yaml and every *.gitlab-ci.yml / .gitlab-ci.yml. A file is
treated as GitHub when it sits under .github/ and as GitLab when its name ends in
gitlab-ci.yml; use --platform to say which for any other path.

Exit codes: 0 no finding at or above --fail-on, 1 at least one, 2 bad input.

The checks are line-based and heuristic: the standard library has no YAML parser. They find
what is visible in the text. zizmor (GitHub Actions) is the fuller linter and
`glab ci lint` / GitLab's CI Lint validate syntax; see SKILL.md.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

SEVERITIES = ("info", "warning", "error")

FULL_SHA = re.compile(r"@[0-9a-f]{40}$")
IMAGE_DIGEST = re.compile(r"@sha256:[0-9a-f]{64}")
SECRET_NAME = re.compile(r"(pass(word|wd)?|secret|token|api[_-]?key|private[_-]?key)", re.I)
GITHUB_OWNED = ("actions/", "github/")

LONG_LIVED_KEYS = re.compile(
    r"credentials_json|GCP_SA_KEY|GOOGLE_CREDENTIALS|GCLOUD_SERVICE_KEY|SERVICE_ACCOUNT_KEY"
    r"|GOOGLE_APPLICATION_CREDENTIALS|activate-service-account\s+--key-file"
    r"|AWS_SECRET_ACCESS_KEY|AZURE_CLIENT_SECRET",
    re.I,
)
PIPE_TO_SHELL = re.compile(r"\b(curl|wget)\b[^|;&\n]*\|\s*(sudo\s+)?(ba|z|da)?sh\b")
PRIVATE_KEY = re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----|AKIA[0-9A-Z]{16}")
DOCKER_LOGIN_PASSWORD = re.compile(r"docker\s+login\b[^\n]*\s(-p|--password)(\s|=)")

# Expressions an attacker controls (branch names, titles, bodies, commit text) per GitHub's
# script-injection guidance. Anything else in `${{ }}` is treated as trusted.
UNTRUSTED = re.compile(
    r"\$\{\{[^}]*github\.(head_ref|event\.(issue\.(title|body)"
    r"|pull_request\.(title|body|head\.(ref|label))|comment\.body|review\.body"
    r"|review_comment\.body|pages\.[^}]*page_name"
    r"|(head_commit|commits[^}]*)\.(message|author\.(email|name))"
    r"|workflow_run\.(head_branch|head_commit\.message)))[^}]*\}\}"
)


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str
    severity: str
    message: str
    fix: str

    def text(self) -> str:
        return (
            f"{self.path}:{self.line}: {self.rule} {self.severity}: {self.message} Fix: {self.fix}"
        )


# ---------------------------------------------------------------- text helpers


def indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def code_lines(text: str) -> list[tuple[int, str]]:
    """(line number, line) for every line that is not a pure comment."""
    return [(n, ln) for n, ln in enumerate(text.splitlines(), 1) if not ln.lstrip().startswith("#")]


def strip_comment(value: str) -> str:
    return re.sub(r"\s+#.*$", "", value).strip().strip("\"'")


def child_block(lines: list[tuple[int, str]], index: int) -> list[tuple[int, str]]:
    """Lines after `index` that are indented deeper than lines[index], until the block ends."""
    base = indent(lines[index][1])
    block: list[tuple[int, str]] = []
    for number, line in lines[index + 1 :]:
        if line.strip() and indent(line) <= base:
            break
        block.append((number, line))
    return block


def step_block(lines: list[tuple[int, str]], index: int) -> list[tuple[int, str]]:
    """Lines from a step's `uses:` line to the end of that step (same or deeper indent)."""
    base = indent(lines[index][1])
    if lines[index][1].lstrip().startswith("- "):
        base += 2
    block = [lines[index]]
    for number, line in lines[index + 1 :]:
        if line.strip() and indent(line) < base:
            break
        block.append((number, line))
    return block


# ---------------------------------------------------------------- GitHub Actions


def check_github(path: Path, text: str) -> list[Finding]:
    out: list[Finding] = []
    shown = str(path)
    lines = code_lines(text)

    def add(line: int, rule: str, severity: str, message: str, fix: str) -> None:
        out.append(Finding(shown, line, rule, severity, message, fix))

    # GHA001 actions pinned to a full commit SHA
    for i, (number, line) in enumerate(lines):
        match = re.match(r"^\s*-?\s*uses:\s*(\S+)", line)
        if not match:
            continue
        ref = strip_comment(match.group(1))
        if ref.startswith("./"):
            continue
        if ref.startswith("docker://"):
            if not IMAGE_DIGEST.search(ref):
                add(
                    number,
                    "GHA001",
                    "warning",
                    f"Docker action '{ref}' is not pinned by digest.",
                    "Append @sha256:<digest>.",
                )
            continue
        if not FULL_SHA.search(ref):
            severity = "warning" if ref.startswith(GITHUB_OWNED) else "error"
            add(
                number,
                "GHA001",
                severity,
                f"'{ref}' is not pinned to a full 40-character commit SHA, so its code can "
                "change without a change here.",
                "Pin to the commit SHA and keep the version in a trailing comment; let "
                "Dependabot or Renovate bump it.",
            )
        if ref.startswith("actions/checkout@"):
            block = "\n".join(ln for _, ln in step_block(lines, i))
            if not re.search(r"persist-credentials:\s*false", block):
                add(
                    number,
                    "GHA008",
                    "info",
                    "actions/checkout keeps the token in the local git config.",
                    "Add `with: persist-credentials: false` unless a later step pushes.",
                )

    # GHA002 permissions
    top_permissions = any(re.match(r"^permissions\s*:", ln) for _, ln in lines)
    for number, line in lines:
        if re.match(r"^\s*permissions:\s*write-all\s*$", line):
            add(
                number,
                "GHA002",
                "error",
                "permissions: write-all gives the token every write scope.",
                "List only the scopes the job needs, each at read or write.",
            )
    if not top_permissions:
        jobs_index = next(
            (i for i, (_, ln) in enumerate(lines) if re.match(r"^jobs:\s*$", ln)), None
        )
        if jobs_index is None:
            add(
                1,
                "GHA002",
                "warning",
                "No `jobs:` key found.",
                "Check that this is a workflow file.",
            )
        else:
            block = child_block(lines, jobs_index)
            job_indent = min((indent(ln) for _, ln in block if ln.strip()), default=2)
            starts = [
                k
                for k, (_, ln) in enumerate(block)
                if indent(ln) == job_indent and ln.strip().endswith(":")
            ]
            for position, k in enumerate(starts):
                end = starts[position + 1] if position + 1 < len(starts) else len(block)
                job_lines = [ln for _, ln in block[k:end]]
                if not any(
                    re.match(rf"^\s{{{job_indent + 2}}}permissions\s*:", ln) for ln in job_lines
                ):
                    name = block[k][1].strip().rstrip(":")
                    add(
                        block[k][0],
                        "GHA002",
                        "warning",
                        f"Job '{name}' has no permissions block and the workflow sets none, "
                        "so it gets the repository's default token permissions.",
                        "Add `permissions: {}` at the top of the workflow, then grant each "
                        "job only what it needs.",
                    )

    # GHA003 dangerous triggers
    for number, line in lines:
        if re.search(r"\bpull_request_target\b", line):
            add(
                number,
                "GHA003",
                "warning",
                "pull_request_target runs with repository secrets and a write token on code "
                "from a pull request.",
                "Use pull_request. If the privileged context is required, never check out or run "
                "the pull request's code in the same workflow.",
            )
            break
    if any(re.search(r"\bpull_request_target\b", ln) for _, ln in lines):
        for number, line in lines:
            if re.search(
                r"ref:\s*\$\{\{\s*github\.(event\.pull_request\.head\.(sha|ref)|head_ref)", line
            ):
                add(
                    number,
                    "GHA003",
                    "error",
                    "A pull_request_target workflow checks out the pull request's own code.",
                    "Check out the base branch only, or split the work into an unprivileged "
                    "pull_request workflow and a privileged workflow_run that reads artifacts.",
                )

    # GHA005 long-lived cloud credentials, GHA007 inherited secrets, GHA013 unsafe commands
    for number, line in lines:
        if LONG_LIVED_KEYS.search(line):
            add(
                number,
                "GHA005",
                "error",
                "A long-lived cloud credential is used.",
                "Use OIDC with Workload Identity Federation (google-github-actions/auth with "
                "workload_identity_provider) so there is no key to leak or rotate.",
            )
        if re.match(r"^\s*secrets:\s*inherit\s*$", line):
            add(
                number,
                "GHA007",
                "warning",
                "`secrets: inherit` passes every secret to the called workflow.",
                "Pass the named secrets the workflow needs.",
            )
        if re.search(r"ACTIONS_ALLOW_UNSECURE_COMMANDS\s*:\s*['\"]?true", line, re.I):
            add(
                number,
                "GHA013",
                "error",
                "Deprecated unsafe workflow commands are re-enabled.",
                "Remove it and use GITHUB_ENV and GITHUB_PATH files with trusted values.",
            )

    # GHA006 script injection in run blocks
    for i, (number, line) in enumerate(lines):
        match = re.match(r"^\s*-?\s*run:\s*(.*)$", line)
        if not match:
            continue
        body = [(number, match.group(1))]
        if match.group(1).strip() in {"|", ">", "|-", ">-", "|+", ">+"}:
            body = child_block(lines, i)
        for body_number, body_line in body:
            if UNTRUSTED.search(body_line):
                add(
                    body_number,
                    "GHA006",
                    "error",
                    "An attacker-controlled value (branch name, title, body or commit text) is "
                    "expanded into a shell script.",
                    "Pass it through `env:` and reference it as a shell variable "
                    '("$TITLE"), never as ${{ ... }} inside `run:`.',
                )
    return out + check_shared(shown, lines)


# ---------------------------------------------------------------- GitLab CI


def _image_findings(shown: str, number: int, value: str) -> list[Finding]:
    value = strip_comment(value)
    if not value:
        return []
    if "$" in value:
        return [
            Finding(
                shown,
                number,
                "GLC001",
                "info",
                f"Image '{value}' uses a variable, so its digest pin cannot be verified here.",
                "Pin the variable's default as image:tag@sha256:<digest>.",
            )
        ]
    if IMAGE_DIGEST.search(value):
        return []
    return [
        Finding(
            shown,
            number,
            "GLC001",
            "warning",
            f"Image '{value}' is not pinned by digest.",
            "Pin as image:tag@sha256:<digest> and let Renovate move the pin.",
        )
    ]


def check_gitlab(path: Path, text: str) -> list[Finding]:
    out: list[Finding] = []
    shown = str(path)
    lines = code_lines(text)

    def add(line: int, rule: str, severity: str, message: str, fix: str) -> None:
        out.append(Finding(shown, line, rule, severity, message, fix))

    job = ""
    image_block_indent: int | None = None
    services_indent: int | None = None
    variables_indent: int | None = None
    mentions_cloud = False
    has_id_tokens = False
    for number, line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        here = indent(line)
        if here == 0 and stripped.endswith(":") and not stripped.startswith("-"):
            job = stripped[:-1]
        # leave pending blocks when indentation returns to their level
        if image_block_indent is not None and here <= image_block_indent:
            image_block_indent = None
        if services_indent is not None and here <= services_indent:
            services_indent = None
        if variables_indent is not None and here <= variables_indent:
            variables_indent = None

        match = re.match(r"^\s*image:\s*(.*)$", line)
        if match:
            if match.group(1).strip():
                out.extend(_image_findings(shown, number, match.group(1)))
            else:
                image_block_indent = here
            continue
        if image_block_indent is not None:
            name = re.match(r"^\s*name:\s*(\S+)", line)
            if name:
                out.extend(_image_findings(shown, number, name.group(1)))
            continue
        if re.match(r"^\s*services:\s*$", line):
            services_indent = here
            continue
        if services_indent is not None:
            item = re.match(r"^\s*-\s*(?:name:\s*)?(\S+)\s*$", line) or re.match(
                r"^\s*name:\s*(\S+)", line
            )
            if item and not item.group(1).endswith(":"):
                out.extend(_image_findings(shown, number, item.group(1)))
                if "dind" in item.group(1):
                    add(
                        number,
                        "GLC010",
                        "info",
                        "Docker-in-Docker needs a privileged runner.",
                        "Run it only on ephemeral, dedicated runners, or build with rootless "
                        "BuildKit or Buildah instead.",
                    )
            continue

        if re.match(r"^\s*variables:\s*$", line):
            variables_indent = here
            continue
        if variables_indent is not None:
            var = re.match(r"^\s*([A-Z][A-Z0-9_]*):\s*(.*?)\s*$", line)
            if var:
                value = strip_comment(var.group(2))
                if SECRET_NAME.search(var.group(1)) and value and not value.startswith("$"):
                    add(
                        number,
                        "GLC004",
                        "error",
                        f"Variable {var.group(1)} holds a literal secret-looking value in the "
                        "pipeline file.",
                        "Define it in Settings > CI/CD > Variables as masked and protected, "
                        "or fetch it from a secrets manager.",
                    )
                if var.group(1) == "CI_DEBUG_TRACE" and value.lower() == "true":
                    add(
                        number,
                        "GLC006",
                        "error",
                        "CI_DEBUG_TRACE prints every command with its variables, secrets "
                        "included, into the job log.",
                        "Remove it. Enable it only on a throwaway pipeline with no secrets.",
                    )
        if re.match(r"^\s*allow_failure:\s*true\s*$", line) and re.search(
            r"scan|sast|secret|trivy|grype|security|sbom|lint|verify", job, re.I
        ):
            add(
                number,
                "GLC007",
                "warning",
                f"Job '{job}' is a security check that is allowed to fail.",
                "Remove allow_failure so a finding stops the pipeline, or record the exception.",
            )
        if re.match(r"^\s*-\s*(env|printenv|set)\s*$", line):
            add(
                number,
                "GLC009",
                "warning",
                "The job prints its whole environment, which can include secrets.",
                "Remove it. Print the specific non-secret values you need.",
            )
        if LONG_LIVED_KEYS.search(line):
            add(
                number,
                "GLC003",
                "error",
                "A long-lived cloud credential is used.",
                "Use `id_tokens:` with Workload Identity Federation so no key is stored.",
            )
        if re.match(r"^\s*id_tokens:\s*$", line):
            has_id_tokens = True
        if re.search(r"googleapis\.com|docker\.pkg\.dev|\bgcloud\b", line):
            mentions_cloud = True

    out.extend(_gitlab_includes(shown, lines))
    if mentions_cloud and not has_id_tokens:
        add(
            1,
            "GLC012",
            "info",
            "The file talks to Google Cloud but declares no `id_tokens:`.",
            "Authenticate with a Workload Identity Federation token (see the reference pipeline).",
        )
    return out + check_shared(shown, lines)


def _gitlab_includes(shown: str, lines: list[tuple[int, str]]) -> list[Finding]:
    out: list[Finding] = []
    for i, (number, line) in enumerate(lines):
        if not re.match(r"^include:", line):
            continue
        inline = line.split(":", 1)[1].strip()
        items: list[list[tuple[int, str]]] = []
        if inline:
            items.append([(number, f"remote: {inline}" if inline.startswith("http") else inline)])
        else:
            for n, ln in child_block(lines, i):
                if ln.lstrip().startswith("- "):
                    items.append([(n, ln.lstrip()[2:])])
                elif items:
                    items[-1].append((n, ln.strip()))
        for item in items:
            first_line = item[0][0]
            keys = {}
            for _, text in item:
                key, _, value = text.partition(":")
                keys[key.strip()] = strip_comment(value)
            if "remote" in keys:
                out.append(
                    Finding(
                        shown,
                        first_line,
                        "GLC002",
                        "warning",
                        f"include remote '{keys['remote']}' is fetched at run time with no "
                        "integrity check.",
                        "Vendor the file into the repository, or include it from a project at "
                        "a commit SHA.",
                    )
                )
            if "project" in keys:
                ref = keys.get("ref", "")
                if not re.fullmatch(r"[0-9a-f]{40}", ref):
                    out.append(
                        Finding(
                            shown,
                            first_line,
                            "GLC002",
                            "warning",
                            f"include from project '{keys['project']}' is not pinned to a commit "
                            f"SHA (ref: '{ref or 'default branch'}').",
                            "Set `ref:` to a full commit SHA or a protected tag.",
                        )
                    )
            if "component" in keys and (
                "@" not in keys["component"] or keys["component"].endswith("@~latest")
            ):
                out.append(
                    Finding(
                        shown,
                        first_line,
                        "GLC002",
                        "warning",
                        f"component '{keys['component']}' has no fixed version.",
                        "Pin the component to an exact version after the @.",
                    )
                )
    return out


# ---------------------------------------------------------------- Both platforms


def check_shared(shown: str, lines: list[tuple[int, str]]) -> list[Finding]:
    out: list[Finding] = []
    for number, line in lines:
        if PIPE_TO_SHELL.search(line):
            out.append(
                Finding(
                    shown,
                    number,
                    "CI001",
                    "warning",
                    "A downloaded script is piped straight into a shell.",
                    "Download it, verify a pinned checksum, then run it.",
                )
            )
        if DOCKER_LOGIN_PASSWORD.search(line):
            out.append(
                Finding(
                    shown,
                    number,
                    "CI002",
                    "warning",
                    "docker login takes the password on the command line, where it appears in "
                    "process listings.",
                    "Use --password-stdin.",
                )
            )
        if PRIVATE_KEY.search(line):
            out.append(
                Finding(
                    shown,
                    number,
                    "CI003",
                    "error",
                    "A private key or cloud access key is written into the file.",
                    "Remove it, rotate the credential, and use short-lived OIDC credentials.",
                )
            )
    return out


# ---------------------------------------------------------------- Discovery and CLI


def detect_platform(path: Path) -> str | None:
    if path.name.endswith("gitlab-ci.yml") or path.name.endswith("gitlab-ci.yaml"):
        return "gitlab"
    if ".github" in path.parts and path.suffix in {".yml", ".yaml"}:
        return "github"
    return None


def discover(paths: list[Path], platform: str | None) -> list[tuple[Path, str]]:
    found: list[tuple[Path, str]] = []
    for path in paths:
        if path.is_dir():
            for candidate in sorted(path.rglob("*")):
                if not candidate.is_file() or ".git" in candidate.relative_to(path).parts:
                    continue
                kind = detect_platform(candidate)
                # Only .github/workflows files are workflows; dependabot.yml and the like are not.
                if kind == "github" and candidate.parent.name != "workflows":
                    continue
                if kind:
                    found.append((candidate, kind))
        elif path.is_file():
            kind = platform or detect_platform(path)
            if kind is None:
                raise ValueError(
                    f"{path}: cannot tell whether this is GitHub Actions or GitLab CI. "
                    "Pass --platform github or --platform gitlab."
                )
            found.append((path, kind))
        else:
            raise FileNotFoundError(
                f"{path}: no such file or directory. Pass a workflow file, a "
                ".gitlab-ci.yml file or a repository directory."
            )
    return found


def run(paths: list[Path], platform: str | None = None) -> list[Finding]:
    findings: list[Finding] = []
    for path, kind in discover(paths, platform):
        text = path.read_text(encoding="utf-8", errors="replace")
        findings.extend(check_github(path, text) if kind == "github" else check_gitlab(path, text))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else "")
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--platform", choices=("github", "gitlab"))
    parser.add_argument("--json", action="store_true", help="print findings as JSON")
    parser.add_argument("--fail-on", choices=SEVERITIES, default="warning")
    args = parser.parse_args(argv)
    try:
        findings = run(args.paths, args.platform)
    except (ValueError, FileNotFoundError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps([asdict(f) for f in findings], indent=2))
    else:
        for finding in findings:
            print(finding.text())
        if not findings:
            print("No findings in the text-level checks. Run zizmor for the full workflow audit.")
    threshold = SEVERITIES.index(args.fail_on)
    return 1 if any(SEVERITIES.index(f.severity) >= threshold for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
