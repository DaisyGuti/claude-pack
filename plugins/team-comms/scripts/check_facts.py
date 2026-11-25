#!/usr/bin/env python3
"""List the facts an edit dropped: numbers, units, links, inline code and code blocks.

The clean-writing skill runs this after an edit, with a copy of the original as BEFORE.
Every item it lists must trace to a cut the user approved. Anything else goes back.

What counts as a fact:

  number      a run of digits in prose, with its separators (14:02, 2.4.1, 12%, 2026-01-05)
  unit        a number and the unit after it (5 MB, 30 s), so a change to 5 GB shows
  link        an http(s) URL or a Markdown link target, keeping balanced parentheses
  code        an inline code span (`--force`, `DB_PASSWORD`)
  code-block  a fenced code block, compared line for line

Each fact is counted. A fact that appeared twice and now appears once is listed, so a cut
repeat reaches the approval check too. Numbers inside code are covered by the code checks.
Ordered-list markers ("1.", "2)") are skipped, so renumbering a list is not reported.

Words are not checked. Names, written-out dates, negations and caveats ("only", "unless")
need a reader.

Usage:
    check_facts.py BEFORE AFTER

Exit codes: 0 nothing dropped, 1 facts dropped (listed on stdout), 2 unusable input.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

KINDS = ("number", "unit", "link", "code", "code-block")
# A fence opens with three or more backticks or tildes, indented at most three spaces. It
# closes on a line of the same character, at least as long (the CommonMark rule).
FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})")
INLINE_CODE = re.compile(r"`([^`\n]+)`")
URL = re.compile(r"https?://[^\s<>`\"']+")
LIST_MARKER = re.compile(r"^\s*(?:#+\s*)?\d+[.)]\s")
NUMBER = re.compile(r"\d+(?:[.,:/-]\d+)*%?")
# Units of measure, where a change alters the fact. Case matters: Mb is megabits.
UNIT_NAMES = (
    r"MB/s|GB/s|Mbps|Gbps|KiB|MiB|GiB|TiB|KB|MB|GB|TB|PB|Kb|Mb|Gb|B|"
    r"ns|µs|us|ms|seconds?|secs?|s|minutes?|mins?|hours?|hrs?|h|days?|weeks?|months?|years?|"
    r"GHz|MHz|kHz|Hz|px|rem|em|pt|mm|cm|km|kg|°C|°F|vCPUs?|cores?|rps|qps|percent"
)
UNIT = re.compile(r"(\d+(?:[.,:/-]\d+)*)\s?(" + UNIT_NAMES + r")(?![\w/])")
TRAILING_PUNCTUATION = ".,;:!?"


def split_code(text: str) -> tuple[list[str], list[str]]:
    """Return (prose lines, fenced code blocks); each block is its lines joined."""
    prose: list[str] = []
    blocks: list[str] = []
    current: list[str] | None = None
    closer = re.compile("")
    for line in text.splitlines():
        if current is None:
            opened = FENCE_OPEN.match(line)
            if opened:
                fence = opened.group(1)
                closer = re.compile(rf"^ {{0,3}}{re.escape(fence[0])}{{{len(fence)},}}\s*$")
                current = []
            else:
                prose.append(line)
        elif closer.match(line):
            blocks.append("\n".join(current))
            current = None
        else:
            current.append(line)
    if current is not None:  # an unclosed fence runs to the end of the file
        blocks.append("\n".join(current))
    return prose, blocks


def trim_url(url: str) -> str:
    """Drop trailing punctuation and any closing parenthesis the URL did not open."""
    while True:
        url = url.rstrip(TRAILING_PUNCTUATION)
        if url.endswith(")") and url.count(")") > url.count("("):
            url = url[:-1]
            continue
        return url


def link_targets(line: str) -> tuple[list[str], str]:
    """Return the Markdown link targets in a line, read with balanced parentheses, and the
    line with each target blanked so the bare-URL scan does not count it twice."""
    targets: list[str] = []
    out: list[str] = []
    i = 0
    while (start := line.find("](", i)) != -1:
        depth, j = 1, start + 2
        while j < len(line) and depth:
            depth += {"(": 1, ")": -1}.get(line[j], 0)
            j += 1
        out.append(line[i : start + 1])
        if depth:  # no closing parenthesis: leave the rest as plain text
            out.append(line[start + 1 :])
            i = len(line)
            break
        target = line[start + 2 : j - 1].strip().split(" ", 1)[0]  # drop a "title"
        if target:
            targets.append(target)
        out.append(" ")
        i = j
    out.append(line[i:])
    return targets, "".join(out)


def facts(text: str) -> dict[str, Counter[str]]:
    prose, blocks = split_code(text)
    found: dict[str, Counter[str]] = {kind: Counter() for kind in KINDS}
    found["code-block"].update(block.strip() for block in blocks if block.strip())
    for line in prose:
        found["code"].update(INLINE_CODE.findall(line))
        targets, bare = link_targets(INLINE_CODE.sub(" ", line))
        found["link"].update(targets)
        found["link"].update(trim_url(m) for m in URL.findall(bare))
        bare = LIST_MARKER.sub(" ", URL.sub(" ", bare))
        found["number"].update(NUMBER.findall(bare))
        found["unit"].update(f"{number} {unit}" for number, unit in UNIT.findall(bare))
    return found


def dropped(before: str, after: str) -> list[tuple[str, str, int, int]]:
    """Each (kind, value, count before, count after) the edit lost, in a stable order."""
    old, new = facts(before), facts(after)
    return [
        (kind, value, old[kind][value], new[kind][value])
        for kind in KINDS
        for value in sorted(old[kind])
        if new[kind][value] < old[kind][value]
    ]


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
    for kind, value, was, now in missing:
        shown = value if "\n" not in value else value.splitlines()[0] + " ..."
        print(f"{args.after}: dropped {kind}: {shown} ({was} before, {now} after)")
    if missing:
        print(
            f"{len(missing)} fact(s) dropped. Restore each one the user did not approve cutting.",
            file=sys.stderr,
        )
        return 1
    print(f"{args.after}: every number, unit, link and code item from {args.before} is kept")
    return 0


if __name__ == "__main__":
    sys.exit(main())
