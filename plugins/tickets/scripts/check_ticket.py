#!/usr/bin/env python3
"""Check a ticket body against the house ticket template before it is filed.

`write-ticket` fills `skills/write-ticket/assets/ticket-template.md`. Its Agent Instructions
sections 1, 2, 3 and 5 are boilerplate that must be copied exactly, section 4 differs only in
the audience on its first bullet, and every top section must hold real content. The workers
that build the ticket rely on that shape, so this script checks it the same way every time.

Usage:
    check_ticket.py BODY_FILE [--template FILE]

Prints JSON {"ok": bool, "problems": [...], "acceptance_bullets": N}. Exit codes: 0 ok,
1 the body has problems, 2 a file could not be read.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

if sys.version_info < (3, 11):  # noqa: UP036  (a clear message on an older python3)
    sys.exit("check_ticket.py needs Python 3.11 or newer; install it and run this again")

DEFAULT_TEMPLATE = (
    Path(__file__).resolve().parent.parent
    / "skills"
    / "write-ticket"
    / "assets"
    / "ticket-template.md"
)
TOP_SECTIONS = ("Context", "Acceptance Criteria", "Out of scope", "Dependencies", "Agent Prompt")
OPTIONAL_SECTIONS = ("Out of scope",)
# More acceptance bullets than this means the ticket should be split (write-ticket step 3).
MAX_ACCEPTANCE_BULLETS = 7
AUDIENCE_PREFIX = (
    "- Follow and reuse existing styles and UI — improve only to meet best industry standards for "
)
INSTRUCTIONS_HEADING = "## Agent Instructions"


def split_sections(text: str) -> tuple[dict[str, str], str]:
    """Return ({top section name: body}, the text from '## Agent Instructions' on)."""
    head, sep, tail = text.partition(INSTRUCTIONS_HEADING)
    instructions = (INSTRUCTIONS_HEADING + tail) if sep else ""
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in head.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return {name: "\n".join(lines).strip() for name, lines in sections.items()}, instructions


def instruction_blocks(text: str) -> dict[str, list[str]]:
    """Split the Agent Instructions text into {'### N. title': lines}."""
    blocks: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        if line.startswith("### "):
            current = line.strip()
            blocks[current] = []
        elif current is not None:
            blocks[current].append(line.rstrip())
    return {k: [ln for ln in v if ln.strip()] for k, v in blocks.items()}


def check(body: str, template: str) -> tuple[list[str], int]:
    """Return (problems, acceptance bullet count) for `body` judged against `template`."""
    problems: list[str] = []
    body_top, body_instr = split_sections(body)
    tmpl_top, tmpl_instr = split_sections(template)

    for name in TOP_SECTIONS:
        if name not in body_top:
            if name not in OPTIONAL_SECTIONS:
                problems.append(f"missing section '## {name}'")
            continue
        content = body_top[name]
        if not content:
            problems.append(f"section '## {name}' is empty")
        elif content == tmpl_top.get(name):
            problems.append(f"section '## {name}' is still the template text")
        elif re.search(r"(?m)^\s*(?:[-*>]\s*)?<[^<>]{12,}>\s*$", content):
            problems.append(
                f"section '## {name}' still has a template placeholder in angle brackets"
            )

    deps = body_top.get("Dependencies", "")
    if deps and not re.search(r"(?m)^Depends on:\s*[^<\s]", deps):
        problems.append(
            "section '## Dependencies' needs a 'Depends on:' line naming issues, or None"
        )

    bullets = len(re.findall(r"(?m)^- ", body_top.get("Acceptance Criteria", "")))
    if bullets > MAX_ACCEPTANCE_BULLETS:
        problems.append(
            f"{bullets} acceptance bullets; split the ticket when the list runs past "
            f"{MAX_ACCEPTANCE_BULLETS}"
        )

    if not body_instr:
        problems.append(f"missing '{INSTRUCTIONS_HEADING}' (copy it from the template)")
        return problems, bullets
    body_blocks = instruction_blocks(body_instr)
    for heading, expected in instruction_blocks(tmpl_instr).items():
        actual = body_blocks.get(heading)
        if actual is None:
            problems.append(f"missing '{heading}' under Agent Instructions")
        elif heading.startswith("### 4."):
            first = next((ln for ln in actual if ln.startswith(AUDIENCE_PREFIX)), None)
            if first is None:
                problems.append(
                    "'### 4.' lost its first bullet ('Follow and reuse existing styles...')"
                )
            elif "<" in first[len(AUDIENCE_PREFIX) :]:
                problems.append("'### 4.' still has the audience placeholder in angle brackets")
            if [ln for ln in actual if not ln.startswith(AUDIENCE_PREFIX)] != [
                ln for ln in expected if not ln.startswith(AUDIENCE_PREFIX)
            ]:
                problems.append("'### 4.' differs from the template beyond its audience")
        elif actual != expected:
            problems.append(f"'{heading}' is not an exact copy of the template")
    return problems, bullets


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("body", type=Path, help="file holding the ticket body")
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    args = parser.parse_args(argv)
    try:
        body = args.body.read_text(encoding="utf-8")
        template = args.template.read_text(encoding="utf-8")
    except OSError as err:
        print(f"error: cannot read {err.filename}: {err.strerror}", file=sys.stderr)
        return 2
    problems, bullets = check(body, template)
    print(
        json.dumps(
            {"ok": not problems, "problems": problems, "acceptance_bullets": bullets}, indent=2
        )
    )
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
