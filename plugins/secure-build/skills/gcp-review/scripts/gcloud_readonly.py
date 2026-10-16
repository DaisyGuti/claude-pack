#!/usr/bin/env python3
"""Run one gcloud command only if it is a known read-only command.

Usage:
    gcloud_readonly.py <gcloud arguments without the leading "gcloud">
    gcloud_readonly.py projects get-iam-policy my-project
    gcloud_readonly.py run services list --project my-project

The wrapper fails closed. It accepts an argument list only when:
  1. the command path (for example "projects get-iam-policy") is on the allowlist below,
  2. every flag is on the flag allowlist and every value uses a safe character set,
  3. no argument contains a shell metacharacter, and
  4. no argument selects a different identity (--impersonate-service-account and similar).

It then runs gcloud with --format=json (where the command supports it), no prompts and no
stdin, and prints gcloud's output. Exit codes:
    0  gcloud ran and succeeded
    1  gcloud ran and failed (stderr is passed through, with a "classified=" line)
    2  the arguments were rejected before anything ran (fail closed)
    3  gcloud is not installed or not on PATH

This wrapper is a guard against mistakes. It does not stop a person or a model from running
gcloud directly. A guarantee that holds every time belongs in a PreToolUse hook.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass

EXIT_OK = 0
EXIT_GCLOUD_FAILED = 1
EXIT_REJECTED = 2
EXIT_NO_GCLOUD = 3

# Command paths that only read. Each entry is the full path of words before any resource name.
# Add a path here only after reading what the command does; a verb that looks harmless can
# still write (for example "asset export" writes to a bucket, so it is absent).
ALLOWED_COMMANDS: frozenset[tuple[str, ...]] = frozenset(
    {
        ("version",),
        ("config", "list"),
        ("config", "get-value"),
        ("auth", "list"),
        ("projects", "list"),
        ("projects", "describe"),
        ("projects", "get-iam-policy"),
        ("projects", "get-ancestors"),
        ("projects", "get-ancestors-iam-policy"),
        ("organizations", "list"),
        ("organizations", "describe"),
        ("organizations", "get-iam-policy"),
        ("resource-manager", "folders", "list"),
        ("resource-manager", "folders", "describe"),
        ("resource-manager", "folders", "get-iam-policy"),
        ("iam", "service-accounts", "list"),
        ("iam", "service-accounts", "describe"),
        ("iam", "service-accounts", "get-iam-policy"),
        ("iam", "service-accounts", "keys", "list"),
        ("iam", "roles", "list"),
        ("iam", "roles", "describe"),
        ("iam", "workload-identity-pools", "list"),
        ("iam", "workload-identity-pools", "describe"),
        ("iam", "workload-identity-pools", "providers", "list"),
        ("iam", "workload-identity-pools", "providers", "describe"),
        ("org-policies", "list"),
        ("org-policies", "describe"),
        ("org-policies", "list-custom-constraints"),
        ("org-policies", "describe-custom-constraint"),
        ("access-context-manager", "policies", "list"),
        ("access-context-manager", "policies", "describe"),
        ("access-context-manager", "perimeters", "list"),
        ("access-context-manager", "perimeters", "describe"),
        ("access-context-manager", "levels", "list"),
        ("access-context-manager", "levels", "describe"),
        ("logging", "sinks", "list"),
        ("logging", "sinks", "describe"),
        ("services", "list"),
        ("artifacts", "repositories", "list"),
        ("artifacts", "repositories", "describe"),
        ("artifacts", "repositories", "get-iam-policy"),
        ("container", "binauthz", "policy", "export"),
        ("container", "binauthz", "attestors", "list"),
        ("container", "binauthz", "attestors", "describe"),
        ("container", "clusters", "list"),
        ("container", "clusters", "describe"),
        ("run", "services", "list"),
        ("run", "services", "describe"),
        ("run", "services", "get-iam-policy"),
        ("run", "jobs", "list"),
        ("run", "jobs", "describe"),
        ("compute", "instances", "list"),
        ("compute", "instances", "describe"),
        ("compute", "firewall-rules", "list"),
        ("compute", "firewall-rules", "describe"),
        ("compute", "networks", "list"),
        ("compute", "networks", "describe"),
        ("compute", "project-info", "describe"),
        ("storage", "buckets", "list"),
        ("storage", "buckets", "describe"),
        ("storage", "buckets", "get-iam-policy"),
        ("sql", "instances", "list"),
        ("sql", "instances", "describe"),
        ("kms", "keyrings", "list"),
        ("kms", "keys", "list"),
        ("kms", "keys", "describe"),
        ("kms", "keys", "get-iam-policy"),
        ("asset", "search-all-resources"),
        ("asset", "search-all-iam-policies"),
        ("asset", "analyze-iam-policy"),
        ("assured", "workloads", "list"),
        ("assured", "workloads", "describe"),
        ("assured", "workloads", "violations", "list"),
        ("assured", "workloads", "violations", "describe"),
        ("scc", "findings", "list"),
    }
)

# These print plain text or YAML, so --format=json is not added for them.
NO_JSON_FORMAT: frozenset[tuple[str, ...]] = frozenset(
    {
        ("container", "binauthz", "policy", "export"),
        ("config", "get-value"),
    }
)

# Words that mean "this changes something or reveals a secret". They give a precise error when a
# command is rejected. The allowlist is the real gate; this list only explains the refusal.
MUTATING_WORDS: frozenset[str] = frozenset(
    {
        "add",
        "add-iam-policy-binding",
        "remove-iam-policy-binding",
        "set-iam-policy",
        "set-policy",
        "set-custom-constraint",
        "delete",
        "delete-custom-constraint",
        "create",
        "update",
        "enable",
        "disable",
        "enable-resource-monitoring",
        "deploy",
        "import",
        "export",
        "ssh",
        "scp",
        "reset",
        "undelete",
        "restore",
        "patch",
        "replace",
        "apply",
        "attach",
        "detach",
        "start",
        "stop",
        "suspend",
        "resume",
        "resize",
        "move",
        "rotate",
        "revoke",
        "activate",
        "login",
        "set",
        "unset",
        "upgrade",
        "rollback",
        "cancel",
        "acknowledge",
        "invoke",
        "execute",
        "connect",
        "copy",
        "cp",
        "mv",
        "rm",
        "rsync",
        "sign-blob",
        "sign-jwt",
        "get-credentials",
        "print-access-token",
        "print-identity-token",
        "application-default",
        "configure-docker",
        "impersonate",
        "submit",
    }
)

# Flags that take a value. The value must use the safe character set below.
VALUE_FLAGS: frozenset[str] = frozenset(
    {
        "--project",
        "--organization",
        "--folder",
        "--location",
        "--region",
        "--zone",
        "--limit",
        "--page-size",
        "--sort-by",
        "--filter",
        "--query",
        "--scope",
        "--policy",
        "--workload",
        "--workload-identity-pool",
        "--iam-account",
        "--managed-by",
        "--created-before",
        "--asset-types",
        "--order-by",
        "--full-resource-name",
        "--identity",
        "--parent",
        "--source",
        "--page-token",
    }
)

# Flags with no value.
BOOLEAN_FLAGS: frozenset[str] = frozenset({"--effective", "--enabled", "--available", "--raw"})

# Flags that change the identity, the output shape or the safety switches. Each has its own
# message, because a person reading the refusal should learn what to do instead.
BLOCKED_FLAGS: dict[str, str] = {
    "--impersonate-service-account": (
        "the wrapper never switches identity. To review as a read-only service account, set up "
        "impersonation in your own gcloud configuration before the review starts"
    ),
    "--account": (
        "the wrapper never switches the gcloud account. Run `gcloud config set account` yourself"
    ),
    "--access-token-file": "the wrapper never accepts a token file",
    "--credential-file-override": "the wrapper never accepts a credential file",
    "--configuration": "the wrapper never switches gcloud configurations",
    "--format": "the wrapper sets the output format itself",
    "--flatten": "the wrapper does not reshape output; analyze the JSON afterwards",
    "--quiet": "the wrapper already runs gcloud without prompts",
    "-q": "the wrapper already runs gcloud without prompts",
    "--verbosity": "the wrapper does not change log verbosity",
    "--log-http": "--log-http prints credentials in headers",
    "--trace-token": "the wrapper never accepts a trace token",
    "--billing-project": "the wrapper does not change the billing project",
}

# Characters that a shell treats as syntax, plus quotes and control characters. Arguments are
# passed to gcloud as a list with no shell, so none of these is needed.
FORBIDDEN_CHARS = frozenset(";&|`$(){}<>\\'\"\n\r\t\x00")
_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9_.:/@=,+%~!-]+$")
# A filter or query expression may contain spaces and wildcards.
_SAFE_EXPRESSION = re.compile(r"^[A-Za-z0-9_.:/@=,+%~!* -]+$")
_EXPRESSION_FLAGS = frozenset({"--filter", "--query"})
MAX_POSITIONALS_AFTER_PATH = 2

# Output of failed calls is classified so a caller can record a gap instead of stopping.
_DENIED = re.compile(
    r"PERMISSION_DENIED|does not have [\w.\-]+ access|403|forbidden|"
    r"caller does not have permission|insufficient permission",
    re.IGNORECASE,
)
_NOT_ENABLED = re.compile(
    r"SERVICE_DISABLED|has not been used in project|API \[[^\]]+\] not enabled|"
    r"is not enabled|accessNotConfigured",
    re.IGNORECASE,
)
_NOT_FOUND = re.compile(r"NOT_FOUND|was not found|404|does not exist|not found", re.IGNORECASE)


class ReadOnlyViolation(ValueError):
    """The arguments are not an accepted read-only gcloud command."""


class GcloudNotFound(RuntimeError):
    """gcloud is not installed or not on PATH."""


@dataclass(frozen=True)
class Outcome:
    returncode: int
    stdout: str
    stderr: str


Runner = Callable[[list[str], dict[str, str], float], Outcome]


def _check_chars(argv: list[str]) -> None:
    for token in argv:
        bad = sorted({c for c in token if c in FORBIDDEN_CHARS})
        if bad:
            shown = " ".join(repr(c) for c in bad)
            raise ReadOnlyViolation(
                f"rejected: argument {token!r} contains shell syntax or quote characters "
                f"({shown}). Pass plain tokens; the wrapper never uses a shell."
            )


def _split(tokens: list[str]) -> tuple[list[str], list[str]]:
    """Return (positional words, normalized flag tokens). Raises on a flag that is not allowed."""
    positionals: list[str] = []
    flags: list[str] = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if not token.startswith("-"):
            positionals.append(token)
            i += 1
            continue
        name, has_value, value = token.partition("=")
        if name in BLOCKED_FLAGS:
            raise ReadOnlyViolation(
                f"rejected: flag {name} is not accepted: {BLOCKED_FLAGS[name]}."
            )
        if name in BOOLEAN_FLAGS:
            if has_value:
                raise ReadOnlyViolation(f"rejected: flag {name} takes no value.")
            flags.append(name)
            i += 1
            continue
        if name in VALUE_FLAGS:
            if not has_value:
                if i + 1 >= len(tokens) or tokens[i + 1].startswith("-"):
                    raise ReadOnlyViolation(f"rejected: flag {name} needs a value.")
                value = tokens[i + 1]
                i += 1
            pattern = _SAFE_EXPRESSION if name in _EXPRESSION_FLAGS else _SAFE_TOKEN
            if not value or not pattern.match(value):
                raise ReadOnlyViolation(
                    f"rejected: value {value!r} for {name} uses characters outside the safe set."
                )
            flags.append(f"{name}={value}")
            i += 1
            continue
        raise ReadOnlyViolation(
            f"rejected: flag {name} is not on the wrapper's flag allowlist. If it is a read-only "
            "flag a review needs, add it to VALUE_FLAGS or BOOLEAN_FLAGS in gcloud_readonly.py."
        )
    return positionals, flags


def _match_path(positionals: list[str]) -> tuple[str, ...] | None:
    best: tuple[str, ...] | None = None
    for path in ALLOWED_COMMANDS:
        if tuple(positionals[: len(path)]) == path and (best is None or len(path) > len(best)):
            best = path
    return best


def validate(argv: list[str]) -> list[str]:
    """Return the exact gcloud arguments to run, or raise ReadOnlyViolation.

    The result has no leading "gcloud". It ends with --format=json and --quiet where they apply.
    """
    tokens = [str(a) for a in argv]
    if tokens and tokens[0] == "gcloud":
        tokens = tokens[1:]
    if not tokens:
        raise ReadOnlyViolation(
            "rejected: no gcloud command given. Pass a read-only command such as "
            "'projects describe PROJECT_ID'."
        )
    _check_chars(tokens)
    positionals, flags = _split(tokens)
    if not positionals:
        raise ReadOnlyViolation("rejected: no command word found, only flags.")
    if positionals[0] in {"alpha", "beta"}:
        raise ReadOnlyViolation(
            f"rejected: release track {positionals[0]!r} commands are not on the allowlist. "
            "Use the general-availability command."
        )
    path = _match_path(positionals)
    if path is None:
        mutating = [w for w in positionals if w in MUTATING_WORDS]
        if mutating:
            raise ReadOnlyViolation(
                f"rejected: {' '.join(positionals[:4])!r} contains the mutating word "
                f"{mutating[0]!r}. This wrapper only runs read-only commands. Draft the "
                "command in the report for a person to run."
            )
        raise ReadOnlyViolation(
            f"rejected: {' '.join(positionals[:4])!r} is not on the read-only allowlist in "
            "gcloud_readonly.py (ALLOWED_COMMANDS). If it only reads, add its full path there "
            "with a test."
        )
    rest = positionals[len(path) :]
    if len(rest) > MAX_POSITIONALS_AFTER_PATH:
        raise ReadOnlyViolation(
            f"rejected: too many positional arguments after {' '.join(path)!r}: {rest}."
        )
    for word in rest:
        if word in MUTATING_WORDS:
            raise ReadOnlyViolation(
                f"rejected: positional argument {word!r} is a mutating word. Check the command."
            )
        if not _SAFE_TOKEN.match(word):
            raise ReadOnlyViolation(
                f"rejected: positional argument {word!r} uses characters outside the safe set."
            )
    result = [*path, *rest, *flags]
    if path not in NO_JSON_FORMAT:
        result.append("--format=json")
    result.append("--quiet")
    return result


def is_text_output(argv: list[str]) -> bool:
    """True when the validated command prints text or YAML instead of JSON."""
    return "--format=json" not in validate(argv)


def child_environment(base: dict[str, str] | None = None) -> dict[str, str]:
    """Environment for the gcloud child process: no prompts, no API-enable offers."""
    env = dict(os.environ if base is None else base)
    env["CLOUDSDK_CORE_DISABLE_PROMPTS"] = "1"
    env["CLOUDSDK_CORE_SHOULD_PROMPT_TO_ENABLE_API"] = "false"
    env["CLOUDSDK_CORE_DISABLE_USAGE_REPORTING"] = "true"
    return env


def classify_failure(stderr: str) -> str:
    """Name why a call failed: denied, not-enabled, not-found or error."""
    if _NOT_ENABLED.search(stderr):
        return "not-enabled"
    if _DENIED.search(stderr):
        return "denied"
    if _NOT_FOUND.search(stderr):
        return "not-found"
    return "error"


def parse_output(stdout: str) -> tuple[object | None, str | None]:
    """Return (parsed JSON, None) or (None, raw text). Empty output parses as an empty list."""
    text = stdout.strip()
    if not text:
        return [], None
    try:
        return json.loads(text), None
    except json.JSONDecodeError:
        return None, text


def _default_runner(cmd: list[str], env: dict[str, str], timeout: float) -> Outcome:
    done = subprocess.run(  # noqa: S603 - argv list, no shell, validated by validate()
        cmd,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        env=env,
        timeout=timeout,
        check=False,
    )
    return Outcome(done.returncode, done.stdout, done.stderr)


def run(argv: list[str], *, timeout: float = 120.0, runner: Runner | None = None) -> Outcome:
    """Validate argv, then run gcloud. Raises ReadOnlyViolation or GcloudNotFound."""
    final = validate(argv)
    binary = shutil.which("gcloud") if runner is None else "gcloud"
    if binary is None:
        raise GcloudNotFound(
            "gcloud was not found on PATH. Install the Google Cloud CLI, then run "
            "`gcloud auth login` (or sign in with the identity your team uses for read-only "
            "review) and retry."
        )
    chosen = runner or _default_runner
    try:
        return chosen([binary, *final], child_environment(), timeout)
    except subprocess.TimeoutExpired:
        return Outcome(1, "", f"timed out after {timeout:.0f} seconds: gcloud {' '.join(final)}")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    try:
        outcome = run(args)
    except ReadOnlyViolation as exc:
        print(f"gcloud_readonly: {exc}", file=sys.stderr)
        return EXIT_REJECTED
    except GcloudNotFound as exc:
        print(f"gcloud_readonly: {exc}", file=sys.stderr)
        return EXIT_NO_GCLOUD
    if outcome.returncode != 0:
        sys.stderr.write(outcome.stderr)
        print(f"gcloud_readonly: classified={classify_failure(outcome.stderr)}", file=sys.stderr)
        return EXIT_GCLOUD_FAILED
    sys.stdout.write(outcome.stdout)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
