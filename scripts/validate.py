#!/usr/bin/env python3
"""Validate the marketplace, every plugin, and every skill, agent and eval file in them.

Two layers run on each plugin:

1. `claude plugin validate --json` on the marketplace root, on each plugin directory and on
   each plugin's `skills/` and `agents/` folder. A plugin directory alone returns no
   component results, so the component folders are validated separately. This repo omits
   `version` everywhere (conventions 38), so the validator's "No version specified" warning
   is allowed; every other error and warning fails the run.
2. A standard-library check of the frontmatter in every SKILL.md, agent file and eval file.
   `claude plugin validate` passes some broken files (a plain description holding a colon,
   an unclosed bracket, a missing description on a skill with a `name`), so the same rules
   are checked here directly.

Usage:
    python3 scripts/validate.py                  # marketplace root, then every plugin
    python3 scripts/validate.py core security    # only these plugins (names under plugins/)
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
ALLOWED_WARNING = "No version specified"
# Anthropic's Claude Code limit for description plus when_to_use (authoring guide rule 4).
MAX_LISTING_CHARS = 1536
MAX_SKILL_NAME = 64
SKILL_NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
RESERVED_WORDS = ("claude", "anthropic")
# A plain YAML scalar may not start with one of these indicator characters.
PLAIN_FORBIDDEN_START = "*&!%@`"
INLINE_REGEX_FLAGS = re.compile(r"\(\?[aiLmsux]+(?:-[imsx]+)?[:)]")
FIELD_LINE = re.compile(r"^([A-Za-z_][\w-]*):(?:[ \t]+(.*))?$")


# ---------------------------------------------------------------------------------------
# Layer 1: claude plugin validate
# ---------------------------------------------------------------------------------------


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


def run_validator(target: Path) -> list[str]:
    """Run `claude plugin validate` on one path; return its blocking problems."""
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


# ---------------------------------------------------------------------------------------
# Layer 2: frontmatter checks in the standard library
# ---------------------------------------------------------------------------------------


@dataclass
class Field:
    """One top-level frontmatter key with the scalar text it holds (empty for lists and maps)."""

    key: str
    line: int
    style: str  # plain, quoted, block, flow or structure
    text: str = ""
    problems: list[str] = field(default_factory=list)


def frontmatter_lines(text: str) -> tuple[list[str], int, str | None]:
    """Return the lines between the two `---` markers, the file line of the first, an error."""
    lines = text.split("\n")
    if not lines or lines[0].rstrip() != "---":
        return [], 0, "the opening `---` must be line 1 of the file"
    for index in range(1, len(lines)):
        if lines[index].rstrip() == "---":
            return lines[1:index], 2, None
    return [], 0, "the frontmatter has no closing `---` line"


def parse_fields(block: list[str], first_line: int) -> list[Field]:
    """Split frontmatter into top-level keys and read each scalar value the way YAML does."""
    groups: list[tuple[int, str, str, list[str]]] = []
    for offset, raw in enumerate(block):
        match = FIELD_LINE.match(raw.rstrip())
        if match:
            groups.append((first_line + offset, match[1], (match[2] or "").strip(), []))
        elif groups:
            groups[-1][3].append(raw)
    return [_read_field(line, key, first, rest) for line, key, first, rest in groups]


def _read_field(line: int, key: str, first: str, rest: list[str]) -> Field:
    continuation = [r.strip() for r in rest if r.strip()]
    if first[:1] in (">", "|"):
        return Field(key, line, "block", " ".join(continuation))
    if first[:1] in ('"', "'"):
        text = " ".join([first, *continuation])
        quote = first[0]
        field_ = Field(key, line, "quoted", text.strip(quote))
        if len(text) < 2 or not text.rstrip().endswith(quote):
            field_.problems.append(f"line {line}: `{key}` opens a {quote} quote that never closes")
        return field_
    if first[:1] in ("[", "{"):
        text = " ".join([first, *continuation])
        field_ = Field(key, line, "flow", text)
        closer = "]" if first[0] == "[" else "}"
        if not text.rstrip().endswith(closer):
            field_.problems.append(f"line {line}: `{key}` opens `{first[0]}` and never closes it")
        return field_
    if not first and (
        not continuation or any(c.startswith("- ") or FIELD_LINE.match(c) for c in continuation)
    ):
        return Field(key, line, "structure")
    text = " ".join([first, *continuation]) if first else " ".join(continuation)
    field_ = Field(key, line, "plain", text)
    if text[:1] in PLAIN_FORBIDDEN_START:
        field_.problems.append(
            f"line {line}: plain `{key}` starts with `{text[0]}`, which YAML reserves; quote it"
        )
    if ": " in text or text.endswith(":"):
        field_.problems.append(
            f"line {line}: plain `{key}` contains a colon followed by a space, which YAML reads"
            " as a nested key; quote the value or use a folded block (`>-`)"
        )
    if " #" in text:
        field_.problems.append(
            f"line {line}: plain `{key}` contains ` #`, which YAML reads as a comment and cuts"
            " the value there; quote the value or use a folded block (`>-`)"
        )
    return field_


def read_frontmatter(path: Path) -> tuple[dict[str, Field], list[str]]:
    """Parse one file's frontmatter; return its fields by key and the problems found."""
    label = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
    block, first_line, error = frontmatter_lines(path.read_text(encoding="utf-8"))
    if error:
        return {}, [f"{label}: {error}"]
    fields = parse_fields(block, first_line)
    problems = [f"{label}: {p}" for f in fields for p in f.problems]
    return {f.key: f for f in fields}, problems


def check_named_component(path: Path, kind: str) -> list[str]:
    """Check a SKILL.md (`kind` = skill) or an agent file (`kind` = agent)."""
    label = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
    fields, problems = read_frontmatter(path)
    if not fields:
        return problems
    for required in ("name", "description"):
        if required not in fields or not fields[required].text.strip():
            problems.append(f"{label}: frontmatter needs a non-empty `{required}`")
    name = fields["name"].text.strip() if "name" in fields else ""
    if name and kind == "skill":
        if not SKILL_NAME.match(name) or len(name) > MAX_SKILL_NAME:
            problems.append(
                f"{label}: skill name `{name}` must be lowercase letters, digits and hyphens,"
                f" {MAX_SKILL_NAME} characters or fewer"
            )
        for word in RESERVED_WORDS:
            if word in name:
                problems.append(f"{label}: skill name `{name}` may not contain `{word}`")
    if name and kind == "agent" and (":" in name or name.startswith("-") or len(name) > 256):
        problems.append(f"{label}: agent name `{name}` may not hold `:` or start with `-`")
    listing = sum(len(fields[k].text) for k in ("description", "when_to_use") if k in fields)
    if listing > MAX_LISTING_CHARS:
        problems.append(
            f"{label}: description plus when_to_use is {listing} characters;"
            f" Claude Code cuts the listing at {MAX_LISTING_CHARS}"
        )
    return problems


def check_eval_prompt(path: Path) -> list[str]:
    """Check an eval case's prompt.md frontmatter for the plain-scalar traps."""
    return read_frontmatter(path)[1]


def check_eval_grader(path: Path) -> list[str]:
    """Check a grader file: plain-scalar traps, and no inline regex flags."""
    label = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
    fields, problems = read_frontmatter(path)
    kind = fields.get("type")
    pattern = fields.get("pattern")
    if (
        kind
        and pattern
        and kind.text.strip() == "regex"
        and INLINE_REGEX_FLAGS.search(pattern.text)
    ):
        problems.append(
            f"{label}: a regex grader rejects inline flags such as `(?i)`; use the `flags:` field"
        )
    return problems


def check_plugin_files(plugin: Path) -> list[str]:
    """Run every standard-library file check for one plugin directory."""
    problems: list[str] = []
    for skill in sorted(plugin.glob("skills/*/SKILL.md")):
        problems += check_named_component(skill, "skill")
    for agent in sorted(plugin.glob("agents/**/*.md")):
        problems += check_named_component(agent, "agent")
    for prompt in sorted(plugin.glob("evals/**/prompt.md")):
        problems += check_eval_prompt(prompt)
    for grader in sorted(plugin.glob("evals/**/graders/*.md")):
        problems += check_eval_grader(grader)
    return problems


# ---------------------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------------------


def validator_targets(plugin: Path) -> list[Path]:
    """The plugin directory plus each component folder that exists."""
    return [plugin, *(plugin / d for d in ("skills", "agents") if (plugin / d).is_dir())]


def label_for(target: Path) -> str:
    return "." if target == ROOT else str(target.relative_to(ROOT))


def main(argv: list[str]) -> int:
    plugins_dir = ROOT / "plugins"
    names = argv or sorted(p.name for p in plugins_dir.iterdir() if p.is_dir())
    plugins: list[Path] = []
    for name in names:
        plugin = plugins_dir / name
        if not plugin.is_dir():
            print(f"error: no plugin directory {plugin}", file=sys.stderr)
            return 1
        plugins.append(plugin)

    targets: list[Path] = [] if argv else [ROOT]
    for plugin in plugins:
        targets += validator_targets(plugin)
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = dict(zip(targets, pool.map(run_validator, targets), strict=True))
    for plugin in plugins:
        results.setdefault(plugin, [])
        results[plugin] = results[plugin] + check_plugin_files(plugin)

    failed = False
    for target, problems in results.items():
        if problems:
            failed = True
            print(f"FAIL {label_for(target)}")
            for line in problems:
                print(f"  {line}")
        elif target in plugins or target == ROOT:
            print(f"ok   {label_for(target)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
