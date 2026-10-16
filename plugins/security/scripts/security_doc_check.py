#!/usr/bin/env python3
"""Check a threat model or a compliance evidence map before it goes to the team.

The checks are the ones a reviewer should not have to do by eye:
  * every NIST SP 800-53 control ID cited exists in the Rev 5 catalog (no invented IDs);
  * a threat model has the sections, the Mermaid diagram with a trust boundary, and a ranked
    threat register in which every threat names a STRIDE category, a risk and a mitigation
    mapped to at least one control;
  * a compliance map carries the evidence-and-gaps notice, uses only the four status words,
    backs every "evidence" status with something to look at, cites its sources, and never
    states that a system is compliant or authorized.

Usage:
    security_doc_check.py DOC --kind threat-model|compliance-map|any --catalog CATALOG.json
    security_doc_check.py DOC --kind any --skip-id-check

Fetch the catalog first with `nist_catalog.py fetch --dest DIR`; the file is
DIR/NIST_SP-800-53_rev5_catalog.json. The ID check is on by default. It stops the run with
exit 2 when no catalog is given, so a missing catalog is never read as "all IDs are fine".

Exit codes: 0 no problems; 1 problems found (one per line, `file:line: message`);
2 usage error or unreadable input.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nist_catalog import load_catalog_path, to_catalog_id  # noqa: E402

# The twenty control families of NIST SP 800-53 Rev 5. An ID-shaped token outside these
# families (HTTP-2, UTF-8, TLS-1) is not a control and is ignored.
FAMILIES = "AC|AT|AU|CA|CM|CP|IA|IR|MA|MP|PE|PL|PM|PS|PT|RA|SA|SC|SI|SR"
CONTROL_ID = re.compile(
    rf"(?<![A-Za-z0-9-])(?:{FAMILIES})-\d{{1,2}}(?:\(\d{{1,2}}\))?(?![A-Za-z0-9])"
)

STATUS_WORDS = (
    "evidence found",
    "partial evidence",
    "no evidence found",
    "not assessable from repo",
)
NEEDS_EVIDENCE = ("evidence found", "partial evidence")
PLACEHOLDERS = {"", "-", "--", "none", "n/a", "na", "tbd", "todo"}
RISK_ORDER = {"critical": 0, "high": 1, "medium": 2, "moderate": 2, "low": 3}
STRIDE = re.compile(
    r"\b(S|T|R|I|D|E|spoofing|tampering|repudiation|information disclosure|"
    r"denial of service|elevation of privilege)\b",
    re.IGNORECASE,
)

# A sentence that says what the document is not may contain the phrases below, so lines
# that carry one of these markers are exempt from the claim check.
NEGATION_MARKERS = ("does not", "not an assessment", "never", "cannot", "no claim")
CLAIM_PATTERNS = [
    re.compile(
        r"\b(is|are|was|remains|been)\s+(now\s+|fully\s+)?(fedramp[- ]|nist[- ]|cmmc[- ])?"
        r"(compliant|authorized|certified|accredited)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bmeets?\s+(all|every)\s+(the\s+)?(requirements|controls)\b", re.IGNORECASE),
    re.compile(r"\bfully\s+implements?\b", re.IGNORECASE),
    re.compile(r"\bsatisfies\s+(the\s+)?controls?\b", re.IGNORECASE),
    re.compile(r"\bATO[- ]ready\b|\bready for (an )?(ATO|authorization)\b", re.IGNORECASE),
]

THREAT_SECTIONS = {
    "a data flow diagram section": ("data flow diagram", "dfd"),
    "a trust boundaries section": ("trust boundar",),
    "an assets section": ("assets",),
    "an abuse cases section": ("abuse case",),
    "a threat register section": ("threat register", "threats"),
    "an assumptions or out-of-scope section": ("assumption", "out of scope"),
}
COMPLIANCE_SECTIONS = {
    "an applicability section": ("applicab",),
    "a sources section": ("sources",),
}


def split_row(line: str) -> list[str]:
    """Split a Markdown table row into trimmed cells, honouring escaped pipes."""
    text = line.strip().replace("\\|", "\x00")
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|"):
        text = text[:-1]
    return [cell.replace("\x00", "|").strip() for cell in text.split("|")]


def is_separator(line: str) -> bool:
    cells = split_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c)


def find_tables(lines: list[str]) -> list[tuple[int, list[str], list[tuple[int, list[str]]]]]:
    """Return (header line number, header cells, [(line number, cells)]) for each table."""
    tables = []
    i = 0
    while i < len(lines) - 1:
        if lines[i].lstrip().startswith("|") and is_separator(lines[i + 1]):
            header = [c.lower() for c in split_row(lines[i])]
            rows = []
            j = i + 2
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                rows.append((j + 1, split_row(lines[j])))
                j += 1
            tables.append((i + 1, header, rows))
            i = j
        else:
            i += 1
    return tables


def column(header: list[str], *keywords: str) -> int | None:
    for index, name in enumerate(header):
        if any(k in name for k in keywords):
            return index
    return None


def check_ids(lines: list[str], known: dict[str, str]) -> list[str]:
    problems = []
    for number, line in enumerate(lines, start=1):
        for match in CONTROL_ID.finditer(line):
            if to_catalog_id(match.group(0)) not in known:
                problems.append(
                    f"{number}: control ID {match.group(0)} is not in the NIST SP 800-53 Rev 5 "
                    "catalog; fix it or remove it"
                )
    return problems


def headings(lines: list[str]) -> list[str]:
    return [line.lstrip("# ").strip().lower() for line in lines if line.startswith("#")]


def check_sections(lines: list[str], required: dict[str, tuple[str, ...]]) -> list[str]:
    found = headings(lines)
    return [
        f"1: missing {label}; add a heading that contains one of {', '.join(map(repr, words))}"
        for label, words in required.items()
        if not any(any(w in h for w in words) for h in found)
    ]


def check_threat_model(lines: list[str]) -> list[str]:
    problems = check_sections(lines, THREAT_SECTIONS)
    text = "\n".join(lines)
    fence = re.search(r"```mermaid\n(.*?)```", text, re.DOTALL)
    if not fence:
        problems.append("1: no ```mermaid block; the data flow diagram must be a Mermaid diagram")
    else:
        body = fence.group(1)
        if "subgraph" not in body:
            problems.append(
                "1: the Mermaid diagram has no `subgraph`; draw each trust boundary as a subgraph"
            )
        if "-->" not in body and "---" not in body:
            problems.append("1: the Mermaid diagram has no data flows (edges)")

    register = None
    for header_line, header, rows in find_tables(lines):
        if column(header, "stride") is not None and column(header, "mitigation") is not None:
            register = (header_line, header, rows)
            break
    if register is None:
        problems.append(
            "1: no threat register table with STRIDE, Risk, Mitigation and Controls columns"
        )
        return problems
    header_line, header, rows = register
    cols = {
        "stride": column(header, "stride"),
        "risk": column(header, "risk"),
        "mitigation": column(header, "mitigation"),
        "controls": column(header, "control"),
    }
    for name, index in cols.items():
        if index is None:
            problems.append(f"{header_line}: the threat register has no {name} column")
    if None in cols.values():
        return problems
    if not rows:
        problems.append(f"{header_line}: the threat register has no rows")
    ranks: list[tuple[int, int]] = []
    for number, cells in rows:
        cells = cells + [""] * (len(header) - len(cells))
        label = cells[0] or f"row at line {number}"
        if not STRIDE.search(cells[cols["stride"]]):
            problems.append(f"{number}: {label} names no STRIDE category")
        risk_word = (
            cells[cols["risk"]].split()[0].lower().strip("()*") if cells[cols["risk"]] else ""
        )
        if risk_word not in RISK_ORDER:
            problems.append(f"{number}: {label} has no risk rating (Critical, High, Medium or Low)")
        else:
            ranks.append((RISK_ORDER[risk_word], number))
        if cells[cols["mitigation"]].strip().lower() in PLACEHOLDERS:
            problems.append(f"{number}: {label} has no mitigation")
        controls = cells[cols["controls"]]
        if not CONTROL_ID.search(controls) and "no mapping" not in controls.lower():
            problems.append(
                f"{number}: {label} maps to no 800-53 control; cite one or write 'no mapping' "
                "with the reason"
            )
    for (prev_rank, _), (rank, number) in zip(ranks, ranks[1:], strict=False):
        if rank < prev_rank:
            problems.append(f"{number}: the register is not ranked; higher risks must come first")
            break
    return problems


def sentences(lines: list[str]) -> list[tuple[int, str]]:
    """Split prose into (starting line number, sentence), so a wrapped sentence stays whole.

    A paragraph is a run of non-blank lines. Table rows and headings are their own units.
    """
    result: list[tuple[int, str]] = []
    paragraph: list[str] = []
    start = 0

    def flush() -> None:
        if paragraph:
            for sentence in re.split(r"(?<=[.!?])\s+", " ".join(paragraph)):
                if sentence.strip():
                    result.append((start, sentence))
            paragraph.clear()

    for number, line in enumerate(lines, start=1):
        if not line.strip() or line.startswith(("#", "|")):
            flush()
            if line.strip():
                result.append((number, line))
            continue
        if not paragraph:
            start = number
        paragraph.append(line.strip())
    flush()
    return result


def check_compliance_map(lines: list[str]) -> list[str]:
    problems = check_sections(lines, COMPLIANCE_SECTIONS)
    lowered = "\n".join(lines).lower()
    for phrase in ("evidence and gaps", "not an assessment"):
        if phrase not in lowered:
            problems.append(f"1: the notice must say '{phrase}' near the top")
    if "http://" not in lowered and "https://" not in lowered:
        problems.append("1: no source URL; cite the fetched document for each framework used")

    for number, sentence in sentences(lines):
        if any(marker in sentence.lower() for marker in NEGATION_MARKERS):
            continue
        for pattern in CLAIM_PATTERNS:
            hit = pattern.search(sentence)
            if hit:
                problems.append(
                    f"{number}: '{hit.group(0)}' reads as a compliance claim; this map reports "
                    "evidence and gaps only, so say what evidence was found instead"
                )
                break

    status_tables = 0
    for _, header, rows in find_tables(lines):
        status_col = column(header, "status")
        if status_col is None or column(header, "control", "requirement", "practice") is None:
            continue
        status_tables += 1
        evidence_col = column(header, "evidence")
        for number, cells in rows:
            cells = cells + [""] * (len(header) - len(cells))
            status = cells[status_col].strip().lower()
            match = next((w for w in STATUS_WORDS if status.startswith(w)), None)
            if match is None:
                problems.append(
                    f"{number}: status '{cells[status_col]}' is not one of: "
                    + ", ".join(STATUS_WORDS)
                )
            elif (
                match in NEEDS_EVIDENCE
                and evidence_col is not None
                and cells[evidence_col].strip().lower() in PLACEHOLDERS
            ):
                problems.append(f"{number}: status '{match}' but the Evidence cell is empty")
    if status_tables == 0:
        problems.append("1: no control table with Control and Status columns")
    return problems


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("doc", help="Markdown file to check")
    parser.add_argument("--kind", required=True, choices=["threat-model", "compliance-map", "any"])
    parser.add_argument("--catalog", help="NIST_SP-800-53_rev5_catalog.json from nist_catalog.py")
    parser.add_argument("--skip-id-check", action="store_true", help="skip the control ID check")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    doc = Path(args.doc)
    try:
        lines = doc.read_text().splitlines()
    except OSError as exc:
        print(f"error: cannot read {doc}: {exc}", file=sys.stderr)
        return 2
    problems: list[str] = []
    if args.skip_id_check:
        print("note: control IDs were NOT verified (--skip-id-check)", file=sys.stderr)
    elif not args.catalog:
        print(
            "error: give --catalog (run `nist_catalog.py fetch --dest DIR` first) or pass "
            "--skip-id-check to skip the ID check on purpose",
            file=sys.stderr,
        )
        return 2
    else:
        try:
            problems += check_ids(lines, load_catalog_path(Path(args.catalog)))
        except (FileNotFoundError, ValueError, KeyError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    if args.kind == "threat-model":
        problems += check_threat_model(lines)
    elif args.kind == "compliance-map":
        problems += check_compliance_map(lines)
    for problem in sorted(problems, key=lambda p: int(p.split(":", 1)[0])):
        print(f"{doc}:{problem}")
    if problems:
        print(f"{len(problems)} problem(s) found", file=sys.stderr)
        return 1
    print(f"{doc}: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
