#!/usr/bin/env python3
"""Check a draft against the team's writing rules and for secrets pasted into it.

Every skill in team-comms runs this on its draft before showing it. The checks:

  contrast     a "X, not Y" style contrast, which the house style bans
  hype         marketing words that add no information
  placeholder  an unfilled [TODO ...] or [confirm ...] marker
  secret       a token, key or ID number that must not reach Slack or a repo

Prose rules skip fenced code blocks and inline code, so code samples are not flagged.
Secret rules scan everything, code included, and print only a masked excerpt.

Usage:
    lint_draft.py FILE            # check a file
    lint_draft.py -               # check stdin
    lint_draft.py --no-prose FILE # secrets only
    lint_draft.py --no-secrets FILE
    lint_draft.py --allow-placeholders FILE   # a draft shown to the user may hold [confirm: ...]

Exit codes: 0 clean, 1 findings (listed on stdout), 2 unusable input.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# Contrast constructions. Each is a heuristic: a hit means "reread this sentence", and the
# author may keep it when the contrast is a real instruction (for example a version pin).
CONTRAST_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "a comma, semicolon or dash followed by 'not'",
        re.compile(r"(?:,|;|—|–|--)\s*not\s+\w+", re.I),
    ),
    (
        "'not just/only X but Y'",
        re.compile(r"\bnot\s+(?:just|only|merely|simply)\b[^.!?\n]{0,100}\bbut\b", re.I),
    ),
    (
        "'isn't X, it's Y'",
        re.compile(
            r"\b(?:isn't|aren't|wasn't|weren't|is not|are not|was not|were not|it's not|"
            r"it is not|this isn't|that isn't|that's not|this is not)\b[^.!?\n]{1,80}"
            r"[.;,—-]\s*(?:it's|it is|this is|that's|they're|instead|rather)\b",
            re.I,
        ),
    ),
    (
        "a sentence that opens with 'Not X.' and then restates",
        re.compile(r"(?:^|[.!?]\s+)(?:[-*]\s+)?Not\s+[^.!?\n]{1,60}\.\s+\w", re.M),
    ),
]

# Words that read as marketing. A hit is a prompt to reword, never an automatic rewrite.
HYPE = re.compile(
    r"\b(?:game[- ]chang\w*|revolutionar\w*|cutting[- ]edge|seamless\w*|leverag(?:e|es|ed|ing)|"
    r"unlock\w*|supercharg\w*|robust|synerg\w*|world[- ]class|best[- ]in[- ]class|next[- ]level|"
    r"delve\w*|elevat(?:e|es|ed|ing)|empower\w*|excited to announce|thrilled|stoked)\b",
    re.I,
)

PLACEHOLDER = re.compile(r"\[(?:TODO|TBD|confirm|fill in|fill)[^\]]*\]|\{\{[^}]*\}\}", re.I)

# Credential and ID formats that are published by their issuers. Patterns are anchored on the
# documented prefixes so ordinary text does not match.
SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("aws-access-key-id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    (
        "github-token",
        re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{22,})\b"),
    ),
    ("gitlab-token", re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b")),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("private-key-block", re.compile(r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----")),
    (
        "jwt",
        re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    ),
    ("us-ssn-shaped-number", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    (
        "secret-assignment",
        # The lookahead requires a digit in the value so `token = os.environ[...]` is not flagged.
        re.compile(
            r"\b(?:password|passwd|secret|api[_-]?key|token)\s*[:=]\s*['\"]?"
            r"(?=[^\s'\"]*\d)[A-Za-z0-9+/_.=-]{8,}",
            re.I,
        ),
    ),
]

FENCE = re.compile(r"^\s*(```|~~~)")
INLINE_CODE = re.compile(r"`[^`\n]*`")
# Shown characters of a masked secret; enough to find it, too few to use it.
MASK_KEEP = 4


@dataclass
class Finding:
    line: int
    rule: str
    message: str
    excerpt: str

    def render(self, source: str) -> str:
        return f"{source}:{self.line}: {self.rule}: {self.message}: {self.excerpt}"


def prose_lines(text: str) -> list[tuple[int, str]]:
    """Return (line number, text) for lines outside fenced code, with inline code blanked."""
    out: list[tuple[int, str]] = []
    in_fence = False
    for number, line in enumerate(text.splitlines(), start=1):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        out.append((number, INLINE_CODE.sub(lambda m: " " * len(m.group(0)), line)))
    return out


def mask(value: str) -> str:
    """Hide all but the first characters of a secret."""
    return value[:MASK_KEEP] + "..." if len(value) > MASK_KEEP else "..."


def excerpt_around(line: str, start: int, end: int, width: int = 40) -> str:
    left = max(0, start - width)
    right = min(len(line), end + width)
    return line[left:right].strip()


def check_prose(text: str, allow_placeholders: bool = False) -> list[Finding]:
    findings: list[Finding] = []
    prose = prose_lines(text)
    for number, line in prose:
        for label, pattern in CONTRAST_PATTERNS:
            for match in pattern.finditer(line):
                findings.append(
                    Finding(
                        number,
                        "contrast",
                        f"contrast construction ({label}); say what the thing is and stop",
                        excerpt_around(line, match.start(), match.end()),
                    )
                )
        for match in HYPE.finditer(line):
            findings.append(
                Finding(number, "hype", "marketing word; use a plain one", match.group(0))
            )
        for match in [] if allow_placeholders else PLACEHOLDER.finditer(line):
            findings.append(Finding(number, "placeholder", "unfilled placeholder", match.group(0)))
    return findings


def check_secrets(text: str) -> list[Finding]:
    findings: list[Finding] = []
    for number, line in enumerate(text.splitlines(), start=1):
        for label, pattern in SECRET_PATTERNS:
            for match in pattern.finditer(line):
                findings.append(
                    Finding(
                        number,
                        "secret",
                        f"looks like a {label}; remove or redact it before this goes anywhere",
                        mask(match.group(0)),
                    )
                )
    return findings


def read_input(target: str) -> tuple[str, str]:
    if target == "-":
        return sys.stdin.read(), "<stdin>"
    path = Path(target)
    if not path.is_file():
        raise FileNotFoundError(
            f"lint_draft.py: no such file: {target}. Pass a path to a draft, or - to read stdin."
        )
    return path.read_text(encoding="utf-8"), target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check a draft for style and secrets.")
    parser.add_argument("target", help="path to the draft, or - for stdin")
    parser.add_argument("--no-prose", action="store_true", help="skip the style rules")
    parser.add_argument("--no-secrets", action="store_true", help="skip the secret scan")
    parser.add_argument(
        "--allow-placeholders",
        action="store_true",
        help="do not flag [TODO ...] and [confirm ...] markers (for a draft not yet sent)",
    )
    args = parser.parse_args(argv)
    try:
        text, source = read_input(args.target)
    except (FileNotFoundError, UnicodeDecodeError) as err:
        print(err, file=sys.stderr)
        return 2
    findings: list[Finding] = []
    if not args.no_prose:
        findings += check_prose(text, args.allow_placeholders)
    if not args.no_secrets:
        findings += check_secrets(text)
    findings.sort(key=lambda f: (f.line, f.rule))
    for finding in findings:
        print(finding.render(source))
    if findings:
        print(f"{len(findings)} finding(s). Fix them and run this again.", file=sys.stderr)
        return 1
    print(f"{source}: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
