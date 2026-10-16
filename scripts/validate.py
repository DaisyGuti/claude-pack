#!/usr/bin/env python3
"""Run `claude plugin validate` on the marketplace and the plugins, allowing one warning.

This repo omits `version` everywhere so updates follow the git commit (conventions 38).
`claude plugin validate --strict` treats the resulting "No version specified" warning as a
failure, so this script runs the validator with `--json` and fails on every error and on
every warning except that one.

Usage:
    python3 scripts/validate.py                  # marketplace root, then every plugin
    python3 scripts/validate.py core security    # only these plugins (names under plugins/)
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
ALLOWED_WARNING = "No version specified"


def find_issues(node: Any, kind: str) -> list[dict[str, Any]]:
    """Collect every entry of the `errors` or `warnings` lists anywhere in the JSON."""
    found: list[dict[str, Any]] = []
    if isinstance(node, dict):
        entries = node.get(kind)
        if isinstance(entries, list):
            found.extend(e for e in entries if isinstance(e, dict))
        for value in node.values():
            found.extend(find_issues(value, kind))
    elif isinstance(node, list):
        for item in node:
            found.extend(find_issues(item, kind))
    return found


def blocking_problems(report: dict[str, Any]) -> list[str]:
    """Return one line per error, and per warning other than the allowed version one."""
    problems = [
        f"error: {e.get('path', '?')}: {e.get('message', e)}" for e in find_issues(report, "errors")
    ]
    for w in find_issues(report, "warnings"):
        if ALLOWED_WARNING in str(w.get("message", "")):
            continue
        problems.append(f"warning: {w.get('path', '?')}: {w.get('message', w)}")
    if report.get("success") is False and not problems:
        problems.append("validator reported failure without a listed error")
    return problems


def validate(target: Path) -> list[str]:
    """Validate one path; return its blocking problems."""
    try:
        proc = subprocess.run(
            ["claude", "plugin", "validate", "--json", str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return ["the `claude` command is not on PATH; install Claude Code (v2.1.289 or later)"]
    if proc.returncode == 2:
        return [f"validator crashed on {target}: {proc.stderr.strip() or proc.stdout.strip()}"]
    try:
        report = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return [f"could not read validator output for {target}: {proc.stdout[:200]!r}"]
    return blocking_problems(report)


def main(argv: list[str]) -> int:
    plugins_dir = ROOT / "plugins"
    names = argv or sorted(p.name for p in plugins_dir.iterdir() if p.is_dir())
    targets: list[Path] = [] if argv else [ROOT]
    for name in names:
        plugin = plugins_dir / name
        if not plugin.is_dir():
            print(f"error: no plugin directory {plugin}", file=sys.stderr)
            return 1
        targets.append(plugin)
    failed = False
    for target in targets:
        problems = validate(target)
        label = target.relative_to(ROOT) if target != ROOT else Path(".")
        if problems:
            failed = True
            print(f"FAIL {label}")
            for line in problems:
                print(f"  {line}")
        else:
            print(f"ok   {label}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
