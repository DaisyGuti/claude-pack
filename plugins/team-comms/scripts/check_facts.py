#!/usr/bin/env python3
"""List the facts an edit dropped: numbers, links, inline code and code blocks.

The clean-writing skill runs this after it edits a file, with a copy of the original as
BEFORE. Every item it lists must trace to a cut the user approved; anything else goes back.

What counts as a fact:

  number      a run of digits in prose, with its separators (14:02, 2.4.1, 12%, 2026-01-05)
  link        an http(s) URL or the target of a Markdown link
  code        an inline code span (`--force`, `DB_PASSWORD`)
  code-block  a fenced code block, compared line for line

Numbers inside code are covered by the code checks. Ordered-list markers ("1.", "2)") are
skipped, so renumbering a list is not reported. A fact counts once however often it appears,
so cutting a repeated sentence is not reported either.

Usage:
    check_facts.py BEFORE AFTER

Exit codes: 0 nothing dropped, 1 facts dropped (listed on stdout), 2 unusable input.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

FENCE = re.compile(r"^\s*(```|~~~)")
INLINE_CODE = re.compile(r"`([^`\n]+)`")
URL = re.compile(r"https?://[^\s<>()\[\]`\"']+")
LINK_TARGET = re.compile(r"\]\(([^)\s]+)")
LIST_MARKER = re.compile(r"^\s*(?:#+\s*)?\d+[.)]\s")
NUMBER = re.compile(r"\d+(?:[.,:/-]\d+)*%?")
TRAILING_PUNCTUATION = ".,;:!?"


def split_code(text: str) -> tuple[list[str], list[str]]:
    """Return (prose lines, fenced code blocks); each block is its lines joined."""
    prose: list[str] = []
    blocks: list[str] = []
    current: list[str] | None = None
    for line in text.splitlines():
        if FENCE.match(line):
            if current is None:
                current = []
            else:
                blocks.append("\n".join(current))
                current = None
            continue
        if current is None:
            prose.append(line)
        else:
            current.append(line)
    if current is not None:  # an unclosed fence runs to the end of the file
        blocks.append("\n".join(current))
    return prose, blocks


def facts(text: str) -> dict[str, set[str]]:
    prose, blocks = split_code(text)
    found: dict[str, set[str]] = {"number": set(), "link": set(), "code": set()}
    found["code-block"] = {block.strip() for block in blocks if block.strip()}
    for line in prose:
        found["code"].update(INLINE_CODE.findall(line))
        bare = INLINE_CODE.sub(" ", line)
        found["link"].update(m.rstrip(TRAILING_PUNCTUATION) for m in URL.findall(bare))
        found["link"].update(LINK_TARGET.findall(bare))
        bare = URL.sub(" ", LINK_TARGET.sub(" ", bare))
        bare = LIST_MARKER.sub(" ", bare)
        found["number"].update(NUMBER.findall(bare))
    return found


def dropped(before: str, after: str) -> list[tuple[str, str]]:
    """Each (kind, value) present in BEFORE and missing from AFTER, in a stable order."""
    old, new = facts(before), facts(after)
    missing: list[tuple[str, str]] = []
    for kind in ("number", "link", "code", "code-block"):
        missing += [(kind, value) for value in sorted(old[kind] - new[kind])]
    return missing


def read(path: str) -> str:
    file = Path(path)
    if not file.is_file():
        raise FileNotFoundError(
            f"check_facts.py: no such file: {path}. Pass the original copy, then the edited file."
        )
    return file.read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="List the facts an edit dropped.")
    parser.add_argument("before", help="a copy of the text before the edit")
    parser.add_argument("after", help="the text after the edit")
    args = parser.parse_args(argv)
    try:
        before, after = read(args.before), read(args.after)
    except (FileNotFoundError, UnicodeDecodeError) as err:
        print(err, file=sys.stderr)
        return 2
    missing = dropped(before, after)
    for kind, value in missing:
        shown = value if "\n" not in value else value.splitlines()[0] + " ..."
        print(f"{args.after}: dropped {kind}: {shown}")
    if missing:
        print(
            f"{len(missing)} fact(s) dropped. Restore each one the user did not approve cutting.",
            file=sys.stderr,
        )
        return 1
    print(f"{args.after}: every number, link and code span from {args.before} is kept")
    return 0


if __name__ == "__main__":
    sys.exit(main())
