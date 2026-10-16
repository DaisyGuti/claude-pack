#!/usr/bin/env python3
"""Check a repo's CLAUDE.md before it is committed.

The project-setup skill runs this on the file it wrote. It fails on the defects that make a
CLAUDE.md wrong or unsafe to commit, and prints notes for things a person should look at.

Usage:
    check_claude_md.py [PATH]    PATH is the CLAUDE.md to check (default: ./CLAUDE.md)

Exit codes: 0 no failures (notes may print), 1 at least one failure, 2 the file cannot be read.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Claude Code's memory documentation targets under 200 lines per CLAUDE.md; longer files
# use more context and reduce adherence. https://code.claude.com/docs/en/memory
MAX_LINES = 200

# Names are for the message only. The matched text is never printed, so a real secret that
# slipped into the file is not copied into a transcript.
SECRET_PATTERNS = {
    "AWS access key id": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "private key block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "GitHub token": re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr|github_pat)_[A-Za-z0-9_]{20,}"),
    "GitLab token": re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}"),
    "Slack token": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    "Google API key": re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    "inline credential": re.compile(
        r"(?i)\b(?:password|passwd|secret|api[_-]?key|token)\s*[:=]\s*['\"]?[A-Za-z0-9/+_-]{12,}"
    ),
}
PERSONAL_PATH = re.compile(r"(?:/Users/[A-Za-z0-9._-]+|/home/[A-Za-z0-9._-]+|[A-Z]:\\Users\\)")
REQUIRED_HEADINGS = {
    "commands": "a Commands section with the repo's real build, test and lint commands",
    "landing": "a Landing changes section (branch, then pull or merge request)",
    "security": "a Security rules section",
}


def code_spans(line: str) -> list[str]:
    return re.findall(r"`([^`]+)`", line)


def headings(lines: list[str]) -> list[str]:
    return [m.group(1).lower() for ln in lines if (m := re.match(r"^#{1,6}\s+(.+?)\s*$", ln))]


def makefile_targets(root: Path) -> set[str] | None:
    path = root / "Makefile"
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    return set(re.findall(r"^([A-Za-z0-9_][A-Za-z0-9_.-]*)\s*:(?!=)", text, re.M))


def package_scripts(root: Path) -> set[str] | None:
    path = root / "package.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError:
        return set()
    scripts = data.get("scripts") if isinstance(data, dict) else None
    return set(scripts) if isinstance(scripts, dict) else set()


# npm lifecycle shortcuts that run a package script without the word `run`.
SHORTCUT_SCRIPTS = {"test", "start", "stop", "restart"}


def cited_script(span: str) -> str | None:
    """The package script a command span runs, or None when it runs no script."""
    match = re.match(r"^(?:npm|pnpm|yarn)\s+(?:(run|run-script)\s+)?([A-Za-z0-9:_-]+)", span)
    if not match:
        return None
    explicit, name = match.groups()
    return name if explicit or name in SHORTCUT_SCRIPTS else None


def check_commands(lines: list[str], root: Path) -> list[str]:
    """Every `make X` and package script the file cites must exist in the repo."""
    failures: list[str] = []
    make = makefile_targets(root)
    scripts = package_scripts(root)
    for number, line in enumerate(lines, start=1):
        for span in code_spans(line):
            if "{{" in span:
                continue
            words = span.split()
            if len(words) >= 2 and words[0] == "make":
                if make is None:
                    failures.append(f"line {number}: `{span}` cites make but there is no Makefile")
                elif words[1] not in make:
                    failures.append(f"line {number}: `{span}`: no target '{words[1]}' in Makefile")
            script = cited_script(span)
            if script is None:
                continue
            if scripts is None:
                failures.append(f"line {number}: `{span}` cites a script but no package.json")
            elif script not in scripts:
                failures.append(f"line {number}: `{span}`: no script '{script}' in package.json")
    return failures


def repo_root(path: Path) -> Path:
    """The directory a CLAUDE.md's commands run from: its own, or the parent of .claude/."""
    parent = path.resolve().parent
    return parent.parent if parent.name == ".claude" else parent


def check_links(lines: list[str], base: Path) -> list[str]:
    """Relative markdown links and `@path` imports must point at files that exist."""
    failures: list[str] = []
    for number, line in enumerate(lines, start=1):
        targets = [t for t in re.findall(r"\]\(([^)\s]+)\)", line)]
        imp = re.match(r"^@(\S*[./]\S*)", line)
        if imp:
            targets.append(imp.group(1))
        for target in targets:
            if re.match(r"^(?:[a-z][a-z0-9+.-]*:|#|\{\{)", target, re.I):
                continue
            if not (base / target.split("#", 1)[0]).exists():
                failures.append(f"line {number}: '{target}' does not exist relative to {base}")
    return failures


def check(path: Path) -> tuple[list[str], list[str]]:
    """Return (failures, notes) for the CLAUDE.md at `path`."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    base = path.parent
    failures: list[str] = []
    notes: list[str] = []

    if len(lines) > MAX_LINES:
        failures.append(
            f"{len(lines)} lines; the target is under {MAX_LINES}. "
            "Link to the document that owns the detail or move it to .claude/rules/."
        )
    for number, line in enumerate(lines, start=1):
        if "{{" in line or "}}" in line or "<!--" in line:
            failures.append(f"line {number}: template placeholder or comment left in the file")
        for name, pattern in SECRET_PATTERNS.items():
            if pattern.search(line):
                failures.append(f"line {number}: looks like a {name}; remove it and rotate it")
        if PERSONAL_PATH.search(line):
            failures.append(f"line {number}: machine-specific path; use a repo-relative path")

    found = headings(lines)
    for key, meaning in REQUIRED_HEADINGS.items():
        if not any(key in h for h in found):
            failures.append(f"missing {meaning}")
    if not re.search(r"pull request|merge request", text, re.I):
        failures.append("the landing rule never mentions a pull request or merge request")

    failures += check_commands(lines, repo_root(path))
    failures += check_links(lines, base)

    unknown = sum(ln.count("UNKNOWN") for ln in lines)
    if unknown:
        notes.append(f"{unknown} UNKNOWN left for a person to fill in")
    if (repo_root(path) / "AGENTS.md").is_file() and not any(
        ln.startswith("@AGENTS.md") for ln in lines
    ):
        notes.append("AGENTS.md exists; import it with a line '@AGENTS.md' instead of copying it")
    return failures, notes


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0
    if len(argv) > 2:
        print(
            "check_claude_md.py: takes at most one argument, the CLAUDE.md path.", file=sys.stderr
        )
        return 2
    path = Path(argv[1]) if len(argv) == 2 else Path("CLAUDE.md")
    try:
        failures, notes = check(path)
    except (OSError, UnicodeDecodeError) as exc:
        print(
            f"check_claude_md.py: cannot read {path}: {exc}. Pass the path to a UTF-8 CLAUDE.md.",
            file=sys.stderr,
        )
        return 2
    for note in notes:
        print(f"NOTE: {note}")
    for failure in failures:
        print(f"FAIL: {failure}")
    print(f"{path}: {len(failures)} failure(s), {len(notes)} note(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
