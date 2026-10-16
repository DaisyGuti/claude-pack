#!/usr/bin/env python3
"""Find the right docs folder, number new files, and check design docs and ADRs.

The design-doc and adr skills call this so file placement, numbering, status edits and the
completeness check are the same every time.

Usage:
    doc_tool.py design locate
    doc_tool.py design new "Rate limiting for the public API"
    doc_tool.py design check docs/design/rate-limiting.md

    doc_tool.py adr locate
    doc_tool.py adr new "Use Postgres for the audit log" --status accepted --supersedes 3
    doc_tool.py adr list
    doc_tool.py adr set-status 3 deprecated
    doc_tool.py adr check docs/decisions/0004-use-postgres-for-the-audit-log.md

All commands run from inside the repository (or pass --root). `new` writes a skeleton full
of [TODO: ...] markers; the skill fills them and `check` fails until none are left.
Output is JSON for `locate`, `new` and `list`, and plain lines for `check`.

Exit codes: 0 ok, 1 `check` found problems, 2 unusable input (the message names the fix).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

PLUGIN = Path(__file__).resolve().parent.parent
DESIGN_TEMPLATE = PLUGIN / "skills" / "design-doc" / "assets" / "design-doc-template.md"
ADR_TEMPLATE = PLUGIN / "skills" / "adr" / "assets" / "madr-template.md"

# Folders already in use by teams, checked in order. The first that exists wins.
DESIGN_DIRS = ["docs/design", "docs/designs", "docs/rfcs", "docs/rfc", "docs/design-docs"]
ADR_DIRS = [
    "docs/adr",
    "docs/adrs",
    "docs/decisions",
    "docs/architecture/decisions",
    "doc/adr",
    "doc/architecture/decisions",
    "architecture/decisions",
    "adr",
]
DEFAULT_DESIGN_DIR = "docs/design"
DEFAULT_ADR_DIR = "docs/decisions"  # the folder MADR itself recommends
DEFAULT_NUMBER_WIDTH = 4
SLUG_MAX = 60  # keeps file names readable in a terminal and a Git UI
NUMBERED = re.compile(r"^(\d+)-.+\.md$")
PLACEHOLDER = re.compile(r"\[TODO[^\]]*\]|\{\{[^}]*\}\}")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
ADR_STATUSES = ("proposed", "accepted", "rejected", "deprecated", "superseded by")

DESIGN_SECTIONS = [
    "Problem",
    "Goals",
    "Non-goals",
    "Options",
    "Recommendation",
    "Security and compliance",
    "Rollout",
    "Open questions",
]
SECURITY_SUBSECTIONS = ["Data handled", "Trust boundaries", "Controls touched", "Gaps and unknowns"]
MIN_OPTIONS = 2
# Phrases that declare a system compliant or authorized. The security section records
# evidence and gaps only, so these are flagged for a person to reword.
COMPLIANCE_CLAIM = re.compile(
    r"\b(?:is|are|fully|now|already)\s+compliant\b"
    r"|\bmeets\s+(?:all\s+)?(?:the\s+)?(?:requirements|controls)\b"
    r"|\bready\s+for\s+(?:authorization|an?\s+ATO)\b",
    re.I,
)


class InputError(ValueError):
    """The caller passed something this script cannot use."""


# ---------------------------------------------------------------- shared helpers


def repo_root(start: Path) -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=start,
        capture_output=True,
        text=True,
        check=False,
    )
    return Path(result.stdout.strip()) if result.returncode == 0 else start


def slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    if len(slug) > SLUG_MAX:
        slug = slug[:SLUG_MAX].rsplit("-", 1)[0] or slug[:SLUG_MAX]
    if not slug:
        raise InputError(f"cannot make a file name from title '{title}'. Use letters or digits.")
    return slug


def pick_dir(root: Path, candidates: list[str], default: str) -> tuple[Path, bool]:
    for candidate in candidates:
        if (root / candidate).is_dir():
            return root / candidate, True
    return root / default, False


def numbered_files(directory: Path) -> list[tuple[int, Path]]:
    if not directory.is_dir():
        return []
    found = [(int(m.group(1)), p) for p in directory.iterdir() if (m := NUMBERED.match(p.name))]
    return sorted(found)


def number_width(files: list[tuple[int, Path]]) -> int:
    widths = [len(NUMBERED.match(p.name).group(1)) for _, p in files]  # type: ignore[union-attr]
    return max(widths) if widths else DEFAULT_NUMBER_WIDTH


def first_heading(text: str) -> str:
    for line in text.splitlines():
        match = HEADING.match(line)
        if match and len(match.group(1)) == 1:
            return match.group(2)
    return ""


def fill(template: str, values: dict[str, str]) -> str:
    """Replace each {{key}} in one pass, so a value that contains {{...}} is left as typed."""
    return re.sub(r"\{\{(\w+)\}\}", lambda m: values.get(m.group(1), m.group(0)), template)


def git_value(root: Path, key: str) -> str:
    result = subprocess.run(
        ["git", "config", key], cwd=root, capture_output=True, text=True, check=False
    )
    return result.stdout.strip()


def sections(text: str, level: int) -> dict[str, list[str]]:
    """Map each heading of `level` to its lines, up to the next heading at or above that level."""
    found: dict[str, list[str]] = {}
    current: str | None = None
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        match = None if in_fence else HEADING.match(line)
        if match and len(match.group(1)) <= level:
            current = match.group(2).strip() if len(match.group(1)) == level else None
            if current is not None:
                found[current] = []
            continue
        if current is not None:
            found[current].append(line)
    return found


def has_body(lines: list[str]) -> bool:
    """True when a section holds text besides blank lines, sub-headings and HTML comments."""
    return any(line.strip() and not line.lstrip().startswith(("#", "<!--")) for line in lines)


def find_section(found: dict[str, list[str]], name: str) -> list[str] | None:
    for heading, lines in found.items():
        if heading.lower().startswith(name.lower()):
            return lines
    return None


# ---------------------------------------------------------------- design docs


def design_locate(root: Path) -> dict[str, Any]:
    directory, exists = pick_dir(root, DESIGN_DIRS, DEFAULT_DESIGN_DIR)
    files = numbered_files(directory)
    return {
        "dir": directory.relative_to(root).as_posix(),
        "exists": exists,
        "numbered": bool(files),
        "next_number": (files[-1][0] + 1) if files else None,
        "number_width": number_width(files),
        "existing": sorted(p.name for p in directory.glob("*.md")) if exists else [],
    }


def design_new(root: Path, title: str, today: str) -> dict[str, Any]:
    info = design_locate(root)
    directory = root / info["dir"]
    slug = slugify(title)
    if info["numbered"]:
        name = f"{info['next_number']:0{info['number_width']}d}-{slug}.md"
    else:
        name = f"{slug}.md"
    target = directory / name
    if target.exists():
        raise InputError(f"{target.relative_to(root)} already exists. Pick a different title.")
    author = git_value(root, "user.name") or "[TODO: author]"
    body = fill(
        DESIGN_TEMPLATE.read_text(encoding="utf-8"),
        {"title": title.strip(), "author": author, "date": today},
    )
    directory.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    return {"path": target.relative_to(root).as_posix(), "created_dir": not info["exists"]}


def design_problems(text: str) -> list[str]:
    problems: list[str] = []
    top = sections(text, 2)
    for name in DESIGN_SECTIONS:
        lines = find_section(top, name)
        if lines is None:
            problems.append(f"missing section '## {name}'")
        elif name != "Options" and name != "Security and compliance" and not has_body(lines):
            problems.append(f"section '## {name}' is empty")
    options = find_section(top, "Options")
    if options is not None:
        options_in_doc = [h for h in sections(text, 3) if h.lower().startswith("option")]
        if len(options_in_doc) < MIN_OPTIONS:
            problems.append(
                f"'## Options' needs at least {MIN_OPTIONS} '### Option ...' subsections "
                f"(found {len(options_in_doc)}); doing nothing counts as one"
            )
    security = find_section(top, "Security and compliance")
    if security is not None:
        sub = sections("\n".join(["## S", *security]), 3)
        for name in SECURITY_SUBSECTIONS:
            lines = find_section(sub, name)
            if lines is None:
                problems.append(f"security section is missing '### {name}'")
            elif not has_body(lines):
                problems.append(f"security subsection '### {name}' is empty")
        for line in security:
            if COMPLIANCE_CLAIM.search(line):
                problems.append(
                    f"security section declares compliance ('{line.strip()[:60]}'); "
                    "record evidence and gaps and leave the decision to the reviewer"
                )
                break
    problems += placeholder_problems(text)
    return problems


def placeholder_problems(text: str) -> list[str]:
    problems = []
    in_fence = False
    for number, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        if not in_fence and (match := PLACEHOLDER.search(line)):
            problems.append(f"line {number}: unfilled placeholder {match.group(0)[:50]}")
    return problems


# ---------------------------------------------------------------- ADRs

FRONT_MATTER_STATUS = re.compile(r'^(status:\s*)(["\']?)(.*?)(["\']?)\s*$', re.I)
INLINE_STATUS = re.compile(r"^(\s*(?:[*-]\s+)?(?:\*\*)?Status(?:\*\*)?:(?:\*\*)?\s*)(.+)$", re.I)


def read_status(text: str) -> str | None:
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for line in lines[1:]:
            if line.strip() == "---":
                break
            if match := FRONT_MATTER_STATUS.match(line):
                return match.group(3)
    for index, line in enumerate(lines):
        if re.match(r"^#{1,3}\s+Status\s*$", line, re.I):
            for follower in lines[index + 1 :]:
                if follower.strip():
                    return follower.strip()
        if match := INLINE_STATUS.match(line):
            return match.group(2).strip()
    return None


def write_status(text: str, status: str) -> str | None:
    """Return `text` with its status replaced, or None when no status line can be found."""
    lines = text.split("\n")
    if lines and lines[0].strip() == "---":
        for index in range(1, len(lines)):
            if lines[index].strip() == "---":
                break
            if match := FRONT_MATTER_STATUS.match(lines[index]):
                lines[index] = f'{match.group(1)}"{status}"'
                return "\n".join(lines)
    for index, line in enumerate(lines):
        if re.match(r"^#{1,3}\s+Status\s*$", line, re.I):
            for follow in range(index + 1, len(lines)):
                if lines[follow].strip():
                    lines[follow] = status
                    return "\n".join(lines)
        if match := INLINE_STATUS.match(line):
            lines[index] = f"{match.group(1)}{status}"
            return "\n".join(lines)
    return None


def adr_records(directory: Path) -> list[dict[str, Any]]:
    records = []
    for number, path in numbered_files(directory):
        text = path.read_text(encoding="utf-8")
        records.append(
            {
                "number": number,
                "file": path.name,
                "title": first_heading(text),
                "status": read_status(text),
            }
        )
    return records


def find_index(directory: Path, records: list[dict[str, Any]]) -> str | None:
    for name in ("README.md", "index.md"):
        candidate = directory / name
        if (
            candidate.is_file()
            and records
            and str(records[0]["file"]) in candidate.read_text(encoding="utf-8")
        ):
            return name
    return None


def adr_locate(root: Path) -> dict[str, Any]:
    directory, exists = pick_dir(root, ADR_DIRS, DEFAULT_ADR_DIR)
    files = numbered_files(directory)
    records = adr_records(directory)
    return {
        "dir": directory.relative_to(root).as_posix(),
        "exists": exists,
        "next_number": (files[-1][0] + 1) if files else 1,
        "number_width": number_width(files),
        "index": find_index(directory, records),
        "records": records,
    }


def adr_new(
    root: Path, title: str, status: str, supersedes: list[int], today: str
) -> dict[str, Any]:
    if not status.lower().startswith(ADR_STATUSES[:4]):
        raise InputError(
            f"status '{status}' is not one of proposed, accepted, rejected, deprecated. "
            "Use --supersedes to mark an older record superseded."
        )
    info = adr_locate(root)
    directory = root / info["dir"]
    width = info["number_width"]
    number = info["next_number"]
    name = f"{number:0{width}d}-{slugify(title)}.md"
    target = directory / name
    if target.exists():
        raise InputError(f"{target.relative_to(root)} already exists. Pick a different title.")
    # Plan first, write second: every record to supersede must exist and carry a status line
    # that can be rewritten, or nothing is written at all.
    by_number = {r["number"]: r for r in info["records"]}
    edits: list[tuple[Path, str]] = []
    links: list[str] = []
    for old in supersedes:
        if old not in by_number:
            known = ", ".join(str(n) for n in sorted(by_number)) or "none"
            raise InputError(f"no ADR number {old} in {info['dir']} (existing: {known}).")
        old_path = directory / by_number[old]["file"]
        marker = f"superseded by [ADR-{number:0{width}d}]({name})"
        updated = write_status(old_path.read_text(encoding="utf-8"), marker)
        if updated is None:
            raise InputError(
                f"{old_path.relative_to(root)} has no status line to update. Add one "
                "(a 'status:' front-matter key or a '## Status' section) and run again."
            )
        edits.append((old_path, updated))
        links.append(f"Supersedes [ADR-{old:0{width}d}]({by_number[old]['file']}).")
    body = fill(
        ADR_TEMPLATE.read_text(encoding="utf-8"),
        {
            "title": title.strip(),
            "status": status,
            "date": today,
            "links": "\n".join(links) if links else "[TODO: links, or delete this section]",
        },
    )
    directory.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    for path, text in edits:
        path.write_text(text, encoding="utf-8")
    return {
        "path": target.relative_to(root).as_posix(),
        "number": number,
        "superseded": [by_number[n]["file"] for n in supersedes],
        "index": info["index"],
    }


def adr_set_status(root: Path, number: int, status: str) -> dict[str, str]:
    info = adr_locate(root)
    match = next((r for r in info["records"] if r["number"] == number), None)
    if match is None:
        raise InputError(f"no ADR number {number} in {info['dir']}.")
    path = root / info["dir"] / match["file"]
    updated = write_status(path.read_text(encoding="utf-8"), status)
    if updated is None:
        raise InputError(f"{path.relative_to(root)} has no status line to update.")
    path.write_text(updated, encoding="utf-8")
    return {"path": path.relative_to(root).as_posix(), "status": status}


def adr_problems(text: str) -> list[str]:
    problems: list[str] = []
    status = read_status(text)
    if status is None:
        problems.append("no status (add a 'status:' key in the front matter)")
    elif not status.lower().startswith(ADR_STATUSES):
        problems.append(f"status '{status}' should start with one of: {', '.join(ADR_STATUSES)}")
    top = sections(text, 2)
    for name in ("Context and Problem Statement", "Considered Options", "Decision Outcome"):
        lines = find_section(top, name)
        if lines is None:
            problems.append(f"missing section '## {name}'")
        elif not has_body(lines):
            problems.append(f"section '## {name}' is empty")
    options = find_section(top, "Considered Options") or []
    if sum(1 for line in options if line.lstrip().startswith(("-", "*"))) < MIN_OPTIONS:
        problems.append(f"'## Considered Options' needs at least {MIN_OPTIONS} options")
    outcome = find_section(top, "Decision Outcome") or []
    if not any(line.lstrip().startswith("Chosen option:") for line in outcome):
        problems.append("'## Decision Outcome' needs a line starting 'Chosen option:'")
    problems += placeholder_problems(text)
    return problems


# ---------------------------------------------------------------- command line


def run_check(path: Path, problems_for: Callable[[str], list[str]]) -> int:
    if not path.is_file():
        raise InputError(f"no such file: {path}. Pass the path that `new` printed.")
    problems = problems_for(path.read_text(encoding="utf-8"))
    for problem in problems:
        print(f"{path}: {problem}")
    if problems:
        print(f"{len(problems)} problem(s). Fix them and run check again.", file=sys.stderr)
        return 1
    print(f"{path}: ok")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Locate, create and check design docs and ADRs.")
    parser.add_argument("--root", type=Path, help="repository root; default is the current repo")
    parser.add_argument("--date", help="override today's date (YYYY-MM-DD), for tests")
    kinds = parser.add_subparsers(dest="kind", required=True)

    design = kinds.add_parser("design").add_subparsers(dest="action", required=True)
    design.add_parser("locate")
    design.add_parser("new").add_argument("title")
    design.add_parser("check").add_argument("file", type=Path)

    adr = kinds.add_parser("adr").add_subparsers(dest="action", required=True)
    adr.add_parser("locate")
    adr.add_parser("list")
    new = adr.add_parser("new")
    new.add_argument("title")
    new.add_argument("--status", default="proposed")
    new.add_argument("--supersedes", type=int, action="append", default=[], metavar="N")
    status = adr.add_parser("set-status")
    status.add_argument("number", type=int)
    status.add_argument("status")
    adr.add_parser("check").add_argument("file", type=Path)
    return parser


def dispatch(args: argparse.Namespace) -> int:
    root = args.root.resolve() if args.root else repo_root(Path.cwd())
    today = args.date or date.today().isoformat()
    if args.action == "check":
        return run_check(args.file, design_problems if args.kind == "design" else adr_problems)
    result: Any
    if args.kind == "design":
        result = (
            design_locate(root) if args.action == "locate" else design_new(root, args.title, today)
        )
    elif args.action == "locate":
        result = adr_locate(root)
    elif args.action == "list":
        result = adr_locate(root)["records"]
    elif args.action == "new":
        result = adr_new(root, args.title, args.status, args.supersedes, today)
    else:
        result = adr_set_status(root, args.number, args.status)
    print(json.dumps(result, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return dispatch(args)
    except InputError as err:
        print(f"doc_tool.py: {err}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
