#!/usr/bin/env python3
"""Build an Accessibility Conformance Report (ACR) on the ITI VPAT 2.5Rev template.

The report covers the WCAG A and AA criteria plus Revised Section 508 chapters 3, 5 and 6.
Everything starts from one evidence file (JSON) that records the test sessions run and, per
row, a status, remarks and the results that support it. This script refuses a claim the
evidence does not carry. It never decides that a product is compliant.

Subcommands:
    acr.py init --wcag 2.0|2.1|2.2 [--web-only] --out evidence.json
    acr.py validate evidence.json [--json]
    acr.py needs-human evidence.json
    acr.py render evidence.json [--format md|html] [--out FILE] [--final]
    acr.py supplement evidence.json [--out FILE.csv]
    acr.py check-template VPAT.docx

Exit codes: 0 success, 1 the evidence has errors (or --final found open items, or the template
differs from the bundled data), 2 an input file could not be read.
"""

from __future__ import annotations

import argparse
import csv
import html
import io
import json
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

STATUSES = ("Supports", "Partially Supports", "Does Not Support", "Not Applicable", "Not Evaluated")
RESULTS = ("pass", "fail", "n/a")
# `by` says who ran a session. Only a person's session can back a Supports claim: a rule
# engine finds a subset of defects, and an assistant reading code is not a tester.
RUNNERS = ("human", "tool", "assistant")
METHODS = (
    "automated",
    "code-review",
    "keyboard",
    "screen-reader",
    "visual",
    "media",
    "pointer",
    "content",
    "documentation",
    "platform",
    "published-procedure",
)
PARTIAL_STATUSES = ("Partially Supports", "Does Not Support")
SEVERITIES = (
    "Critical Accessibility Barrier",
    "Major Accessibility Issue",
    "Minor Accessibility Issue",
)
# The nine functional performance groups the GSA issue supplement lists (Section 508 302.1-302.9).
USER_GROUPS = (
    "Without Vision",
    "With Limited Vision",
    "Without Perception of Color",
    "Without Hearing",
    "With Limited Hearing",
    "Without Speech",
    "With Limited Manipulation",
    "With Limited Reach and Strength",
    "With Limited Language, Cognitive, and Learning Abilities",
)
WCAG_VERSIONS = ("2.0", "2.1", "2.2")
REQUIRED_HEADER = ("company", "product", "report_date", "description", "contact")
PLACEHOLDER = re.compile(r"^\s*(todo|tbd|\[.*\])?\s*$", re.IGNORECASE)
# Word documents unzip to a few MB at most; the cap only stops a malformed archive.
MAX_DOCX_BYTES = 100 * 1024 * 1024
# Enough open items to see the pattern; the rest are one command away.
OPEN_ITEMS_SHOWN = 5


class InputError(Exception):
    """An input file that cannot be read; the message names the file and the fix."""


# --- data --------------------------------------------------------------------------------


@dataclass(frozen=True)
class Row:
    id: str
    title: str
    section: str  # wcag-a, wcag-aa, ch3, ch5, ch6
    kind: str  # row, heading, crossref, template
    hint: tuple[str, ...] = ()
    since: str = "2.0"
    level: str = ""


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as err:
        raise InputError(f"cannot read {path}: {err.strerror}. Check the path.") from err
    except json.JSONDecodeError as err:
        raise InputError(
            f"{path} is not valid JSON (line {err.lineno}, column {err.colno}). Fix the syntax."
        ) from err


def load_criteria() -> dict[str, Any]:
    data = read_json(DATA_DIR / "criteria.json")
    assert isinstance(data, dict)
    return data


def load_text() -> dict[str, Any]:
    data = read_json(DATA_DIR / "vpat-text.json")
    assert isinstance(data, dict)
    return data


def version_key(version: str) -> tuple[int, int]:
    major, minor = version.split(".")
    return int(major), int(minor)


def table_rows(wcag_version: str) -> list[tuple[str, list[Row]]]:
    """The report's tables in template order: (heading, rows), headings included for 508."""
    criteria = load_criteria()
    limit = version_key(wcag_version)
    wcag = [w for w in criteria["wcag"] if version_key(w["since"]) <= limit]
    tables: list[tuple[str, list[Row]]] = []
    for level, heading in (
        ("A", "Table 1: Success Criteria, Level A"),
        ("AA", "Table 2: Success Criteria, Level AA"),
    ):
        rows = [
            Row(
                id=w["id"],
                title=w["title"],
                section=f"wcag-{level.lower()}",
                kind="template" if w.get("template_answers") else "row",
                hint=tuple(w["hint"]),
                since=w["since"],
                level=level,
            )
            for w in wcag
            if w["level"] == level
        ]
        tables.append((heading, rows))
    for key, section in (("chapter3", "ch3"), ("chapter5", "ch5"), ("chapter6", "ch6")):
        chapter = criteria["section508"][key]
        rows = [
            Row(r["id"], r["title"], section, r["kind"], tuple(r.get("hint", ())))
            for r in chapter["rows"]
        ]
        tables.append((chapter["title"], rows))
    return tables


def answerable_rows(wcag_version: str) -> dict[str, Row]:
    return {r.id: r for _, rows in table_rows(wcag_version) for r in rows if r.kind == "row"}


# --- findings ----------------------------------------------------------------------------


@dataclass
class Findings:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    open_items: list[str] = field(default_factory=list)


def blank(value: object) -> bool:
    return not isinstance(value, str) or bool(PLACEHOLDER.match(value))


def wcag_version_of(doc: dict[str, Any], findings: Findings) -> str:
    version = doc.get("wcag_version")
    if version not in WCAG_VERSIONS:
        findings.errors.append(
            f'"wcag_version" must be one of {", ".join(WCAG_VERSIONS)} (got {version!r}). '
            "Use 2.0 for the Revised Section 508 edition."
        )
        return "2.0"
    return str(version)


def check_report_header(doc: dict[str, Any], findings: Findings) -> None:
    report = doc.get("report")
    if not isinstance(report, dict):
        findings.errors.append('"report" must be an object with the report header fields.')
        return
    for name in REQUIRED_HEADER:
        if blank(report.get(name)):
            findings.open_items.append(f'Report field "{name}" is empty. The VPAT requires it.')
    if blank(report.get("vpat_version")):
        findings.open_items.append(
            'Report field "vpat_version" is empty. Set it from the edition fetched from itic.org.'
        )
    elif report["vpat_version"] != load_criteria()["vpat"]["version"]:
        findings.warnings.append(
            f'"vpat_version" is {report["vpat_version"]!r} but the bundled rows were verified '
            f"against {load_criteria()['vpat']['version']}. Run check-template on the edition "
            "you used."
        )
    if report.get("product_has_hardware"):
        findings.errors.append(
            '"product_has_hardware" is true. This skill reports web products only; Chapter 4 '
            "(Hardware) needs the VPAT template filled in directly."
        )


def check_sessions(doc: dict[str, Any], findings: Findings) -> dict[str, dict[str, Any]]:
    sessions: dict[str, dict[str, Any]] = {}
    entries = doc.get("sessions", [])
    if not isinstance(entries, list):
        findings.errors.append('"sessions" must be a list of test sessions.')
        return sessions
    for index, entry in enumerate(entries):
        where = f"sessions[{index}]"
        if not isinstance(entry, dict):
            findings.errors.append(f"{where} must be an object.")
            continue
        sid = entry.get("id")
        if blank(sid):
            findings.errors.append(f'{where} has no "id".')
            continue
        where = f'session "{sid}"'
        if sid in sessions:
            findings.errors.append(f"{where} is defined twice. Session ids must be unique.")
        if entry.get("method") not in METHODS:
            findings.errors.append(f'{where}: "method" must be one of {", ".join(METHODS)}.')
        by = entry.get("by")
        if by not in RUNNERS:
            findings.errors.append(f'{where}: "by" must be one of {", ".join(RUNNERS)}.')
        elif by == "human" and blank(entry.get("tester")):
            findings.errors.append(
                f'{where} is marked "human" but names no "tester". Give the role and the '
                "assistive technology used."
            )
        elif by == "tool" and blank(entry.get("tool")):
            findings.errors.append(f'{where} is marked "tool" but names no "tool".')
        if blank(entry.get("date")):
            findings.warnings.append(f'{where} has no "date".')
        sessions[str(sid)] = entry
    return sessions


def human_results(row: dict[str, Any], sessions: dict[str, dict[str, Any]]) -> set[str]:
    """Results (pass/fail) recorded by sessions that a person ran."""
    found: set[str] = set()
    for item in row.get("evidence", []):
        if isinstance(item, dict) and sessions.get(item.get("session"), {}).get("by") == "human":
            found.add(str(item.get("result")))
    return found


def check_row(
    rid: str, row: Any, info: Row, sessions: dict[str, dict[str, Any]], findings: Findings
) -> None:
    label = f"{rid} {info.title}"
    if not isinstance(row, dict):
        findings.errors.append(
            f"{label}: the row must be an object with status, remarks, evidence."
        )
        return
    status = row.get("status")
    if status not in STATUSES:
        findings.errors.append(f'{label}: "status" must be one of {", ".join(STATUSES)}.')
        return
    evidence = row.get("evidence", [])
    if not isinstance(evidence, list):
        findings.errors.append(f'{label}: "evidence" must be a list.')
        return
    results: list[str] = []
    for item in evidence:
        if not isinstance(item, dict) or item.get("session") not in sessions:
            named = item.get("session") if isinstance(item, dict) else item
            findings.errors.append(
                f'{label}: evidence points at session {named!r}, which is not in "sessions". '
                "Add the session or fix the id."
            )
            continue
        if item.get("result") not in RESULTS:
            findings.errors.append(
                f'{label}: evidence "result" must be one of {", ".join(RESULTS)}.'
            )
            continue
        results.append(str(item["result"]))
    remarks = row.get("remarks")
    human = human_results(row, sessions)

    if status == "Supports":
        used = {
            sessions[i["session"]]["method"]
            for i in evidence
            if isinstance(i, dict)
            and i.get("result") == "pass"
            and sessions.get(i.get("session"), {}).get("by") == "human"
        }
        if used and info.hint and not used & {*info.hint, "published-procedure"}:
            findings.warnings.append(
                f"{label}: the person-run checks behind Supports are {', '.join(sorted(used))}, "
                f"but this row is usually settled by {', '.join(info.hint)}. Confirm the evidence "
                "covers what the criterion asks."
            )
        if "fail" in results:
            findings.errors.append(
                f"{label}: marked Supports but the evidence holds a failing result. Supports "
                "means no known defects. Change the status, or fix the product and re-test."
            )
        if "pass" not in human:
            hint = ", ".join(info.hint) or "a person's check"
            findings.errors.append(
                f"{label}: marked Supports without a passing check run by a person. Add a "
                f'session with "by": "human" and its result (usual check: {hint}), or set the '
                "status to Not Evaluated."
            )
    elif status in ("Partially Supports", "Does Not Support"):
        if "fail" not in results:
            findings.errors.append(
                f"{label}: marked {status} without a failing result in the evidence. Record the "
                "session that found the defect."
            )
        if blank(remarks):
            findings.errors.append(
                f"{label}: marked {status} without remarks. The VPAT requires the remarks to name "
                "the functions with issues and how they fail."
            )
    elif status == "Not Applicable":
        if blank(remarks):
            findings.errors.append(
                f"{label}: marked Not Applicable without remarks. Say why it does not apply."
            )
        if info.section.startswith("wcag"):
            findings.warnings.append(
                f"{label}: Not Applicable on a WCAG row. The VPAT notes that Supports fits when "
                "there is no content the criterion applies to."
            )
    elif status == "Not Evaluated":
        hint = ", ".join(info.hint) or "a person's check"
        findings.open_items.append(
            f"{rid} {info.title}: Not Evaluated. Needs a person (usual check: {hint})."
        )


def check_issues(doc: dict[str, Any], rows: dict[str, Row], findings: Findings) -> set[str]:
    """Check the optional issue list; return the row ids that some issue covers."""
    covered: set[str] = set()
    issues = doc.get("issues", [])
    if not isinstance(issues, list):
        findings.errors.append('"issues" must be a list.')
        return covered
    seen: set[str] = set()
    for index, issue in enumerate(issues):
        where = f"issues[{index}]"
        if not isinstance(issue, dict) or blank(issue.get("id")):
            findings.errors.append(f'{where} needs an object with an "id".')
            continue
        where = f'issue "{issue["id"]}"'
        if issue["id"] in seen:
            findings.errors.append(f"{where} is defined twice.")
        seen.add(issue["id"])
        if issue.get("severity") not in SEVERITIES:
            findings.errors.append(f'{where}: "severity" must be one of: {"; ".join(SEVERITIES)}.')
        if blank(issue.get("summary")):
            findings.errors.append(f'{where}: "summary" is empty. Say what is wrong in one line.')
        if blank(issue.get("area")):
            findings.errors.append(
                f'{where}: "area" is empty. Name the page, screen or flow and how far it spreads.'
            )
        if blank(issue.get("workaround")):
            findings.errors.append(
                f'{where}: "workaround" is empty. The GSA supplement asks for it; write '
                '"None known" when there is none.'
            )
        users = issue.get("impacted_users")
        if not isinstance(users, list) or not users or any(u not in USER_GROUPS for u in users):
            findings.errors.append(
                f'{where}: "impacted_users" must be a non-empty list drawn from: '
                f"{'; '.join(USER_GROUPS)}."
            )
        criteria = issue.get("criteria")
        if not isinstance(criteria, list) or not criteria:
            findings.errors.append(f'{where}: "criteria" must list the row ids the issue affects.')
            continue
        for cid in criteria:
            if cid not in rows:
                findings.errors.append(f"{where}: {cid!r} is not an answerable row id.")
            else:
                covered.add(cid)
    return covered


def validate(doc: object) -> Findings:
    findings = Findings()
    if not isinstance(doc, dict):
        findings.errors.append("The evidence file must hold a JSON object at the top level.")
        return findings
    version = wcag_version_of(doc, findings)
    check_report_header(doc, findings)
    sessions = check_sessions(doc, findings)
    report = doc.get("report") if isinstance(doc.get("report"), dict) else {}
    if not sessions and blank(report.get("evaluation_methods")):
        findings.open_items.append(
            'No test sessions and no "evaluation_methods" text. The VPAT requires a description '
            "of the evaluation methods used."
        )
    rows = answerable_rows(version)
    entries = doc.get("rows", {})
    if not isinstance(entries, dict):
        findings.errors.append('"rows" must be an object keyed by criterion id.')
        entries = {}
    for rid, row in entries.items():
        if rid not in rows:
            findings.errors.append(
                f"{rid}: not an answerable row for WCAG {version} A/AA or Section 508 "
                "chapters 3, 5 and 6. Heading rows, cross-reference rows (501.1, 504.2, 602.3) "
                "and 4.1.1 are answered by the template, and criteria added after WCAG "
                f"{version} are not in this report."
            )
            continue
        check_row(rid, row, rows[rid], sessions, findings)
    for rid, info in rows.items():
        if rid not in entries:
            findings.open_items.append(
                f"{rid} {info.title}: no row in the evidence file, so it reads Not Evaluated."
            )
    prefilled = sorted(
        r for r, row in entries.items() if isinstance(row, dict) and row.get("prefilled")
    )
    if prefilled:
        findings.open_items.append(
            f"{len(prefilled)} row(s) were pre-filled by the web-only profile "
            f"({prefilled[0]} to {prefilled[-1]}). Confirm them with the product team, then "
            'delete each "prefilled" key.'
        )
    unevaluated = sum(
        1
        for rid in rows
        if not isinstance(entries.get(rid), dict) or entries[rid].get("status") == "Not Evaluated"
    )
    if unevaluated:
        findings.warnings.append(
            f"{unevaluated} A/AA or Section 508 row(s) read Not Evaluated. The VPAT allows that "
            "answer only for WCAG Level AAA, so the report stays a draft until a person tests them."
        )
    covered = check_issues(doc, rows, findings)
    if doc.get("issues"):
        for rid, row in entries.items():
            partial = isinstance(row, dict) and row.get("status") in PARTIAL_STATUSES
            if partial and rid not in covered:
                findings.warnings.append(
                    f'{rid}: {row["status"]} but no entry in "issues" covers it. The GSA '
                    "supplement lists every known issue."
                )
    return findings


# --- init and needs-human ----------------------------------------------------------------

_WEB_ONLY_502_503 = (
    "Web-only product. The VPAT instructions state that 502 and 503 do not apply to a web-only "
    "application."
)
WEB_ONLY_REMARKS = {
    "502": _WEB_ONLY_502_503,
    "503": _WEB_ONLY_502_503,
    "504": "The product is not an authoring tool.",
}


def scaffold(wcag_version: str, web_only: bool) -> dict[str, Any]:
    rows: dict[str, Any] = {}
    for rid in answerable_rows(wcag_version):
        row: dict[str, Any] = {"status": "Not Evaluated", "remarks": "", "evidence": []}
        if web_only and rid.split(".")[0] in WEB_ONLY_REMARKS:
            row = {
                "status": "Not Applicable",
                "remarks": WEB_ONLY_REMARKS[rid.split(".")[0]],
                "evidence": [],
                "prefilled": True,
            }
        rows[rid] = row
    return {
        "report": {
            "company": "",
            "product": "",
            "report_date": "",
            "description": "",
            "contact": "",
            "notes": "",
            "evaluation_methods": "",
            "vpat_version": load_criteria()["vpat"]["version"],
            "legal_disclaimer": "",
            "product_has_hardware": False,
        },
        "wcag_version": wcag_version,
        "sessions": [],
        "rows": rows,
        "issues": [],
    }


def rows_needing_a_person(doc: dict[str, Any]) -> list[tuple[Row, str, str]]:
    """Rows where a person's check is still missing: (row, current status, why)."""
    findings = Findings()
    version = wcag_version_of(doc, findings)
    sessions = check_sessions(doc, findings)
    entries = doc.get("rows", {}) if isinstance(doc.get("rows"), dict) else {}
    needed: list[tuple[Row, str, str]] = []
    for rid, info in answerable_rows(version).items():
        row = entries.get(rid)
        status = row.get("status") if isinstance(row, dict) else "Not Evaluated"
        if status == "Not Applicable":
            if isinstance(row, dict) and row.get("prefilled"):
                needed.append((info, str(status), "confirm the pre-filled answer"))
            continue
        if status == "Does Not Support":
            continue
        if isinstance(row, dict) and human_results(row, sessions):
            continue
        why = "not evaluated" if status in (None, "Not Evaluated") else "no check run by a person"
        needed.append((info, str(status), why))
    return needed


# --- rendering ---------------------------------------------------------------------------


def edition_key(wcag_version: str) -> str:
    return "508" if wcag_version == "2.0" else "international"


def session_line(entry: dict[str, Any]) -> str:
    by = entry.get("by")
    if by == "human":
        who = entry.get("tester")
    else:
        who = entry.get("tool") or ("AI assistant" if by == "assistant" else by)
    parts = [f"{entry.get('method')} ({entry.get('by')}: {who})"]
    if entry.get("date"):
        parts.append(str(entry["date"]))
    line = ", ".join(parts)
    if entry.get("scope"):
        line += f": {entry['scope']}"
    if entry.get("ref"):
        line += f" [{entry['ref']}]"
    return line


def row_cells(info: Row, row: Any, wcag_version: str) -> tuple[str, str, str]:
    """Return (criteria cell, conformance cell, remarks cell) as plain text."""
    text = load_text()
    suffix = ""
    if info.section.startswith("wcag") and info.since != "2.0":
        suffix = f" (Level {info.level}, WCAG {info.since}" + (
            " only)" if info.since == "2.2" else " and 2.2)"
        )
    elif info.section.startswith("wcag"):
        suffix = f" (Level {info.level})"
    criteria = f"{info.id} {info.title}{suffix}"
    if info.kind == "template":
        return criteria, "Supports", text["editions"][edition_key(wcag_version)]["parsing_remark"]
    if info.kind == "crossref":
        return criteria, "See WCAG 2.x section", text["crossref_remark"]
    if info.kind == "heading":
        return criteria, "Heading cell - no response required", ""
    status = row.get("status") if isinstance(row, dict) else "Not Evaluated"
    remarks = (row.get("remarks") or "") if isinstance(row, dict) else ""
    if status == "Not Evaluated" and not remarks:
        hint = ", ".join(info.hint)
        remarks = "Not evaluated." + (
            f" A person needs to run this check ({hint})." if hint else ""
        )
    prefix = "Web: " if info.section.startswith("wcag") else ""
    return criteria, f"{prefix}{status}", f"{prefix}{remarks}" if remarks else ""


def blocks(doc: dict[str, Any], findings: Findings) -> tuple[str, list[tuple[str, Any]]]:
    """Return (page title, ordered blocks). A block is (kind, payload).

    Kinds: h1, h2, h3 and p (text), note (draft banner), field (label, value),
    table (caption, header, rows), ul (items).
    """
    text = load_text()
    version = str(doc.get("wcag_version", "2.0"))
    edition = text["editions"][edition_key(version)]
    report = doc.get("report", {})
    sessions = {s["id"]: s for s in doc.get("sessions", []) if isinstance(s, dict) and "id" in s}
    rows = doc.get("rows", {}) if isinstance(doc.get("rows"), dict) else {}

    def val(name: str) -> str:
        value = report.get(name)
        return value.strip() if isinstance(value, str) and value.strip() else "[not provided]"

    title = f"{val('company')} Accessibility Conformance Report"
    out: list[tuple[str, Any]] = [
        ("h1", title),
        ("p", edition["title"]),
        ("p", f"(Based on VPAT® Version {val('vpat_version')})"),
    ]
    if findings.open_items:
        out.append(
            (
                "note",
                f"DRAFT. Not ready to publish: {len(findings.open_items)} open item(s) are "
                'listed under "Open items" at the end of this report.',
            )
        )
    out += [
        ("field", ("Name of Product/Version", val("product"))),
        ("field", ("Report Date", val("report_date"))),
        ("field", ("Product Description", val("description"))),
        ("field", ("Contact Information", val("contact"))),
        ("field", ("Notes", (report.get("notes") or "").strip())),
    ]
    methods = (report.get("evaluation_methods") or "").strip()
    out.append(("field", ("Evaluation Methods Used", methods)))
    if sessions:
        out.append(("ul", [session_line(s) for s in sessions.values()]))

    out.append(("h2", "Applicable Standards/Guidelines"))
    out.append(
        (
            "p",
            "This report covers the degree of conformance for the following accessibility "
            "standards/guidelines.",
        )
    )
    standards: list[list[str]] = []
    for wcag in WCAG_VERSIONS:
        if version_key(wcag) <= version_key(version):
            standards.append(
                [
                    text["standards"]["wcag"].format(version=wcag),
                    "Level A (Yes), Level AA (Yes), Level AAA (No)",
                ]
            )
    standards.append([text["standards"]["section508"], "(Yes)"])
    if version != "2.0":
        standards.append([text["standards"]["en301549"], "(No)"])
    out.append(
        (
            "table",
            (
                "Standards and guidelines covered",
                ["Standard/Guideline", "Included In Report"],
                standards,
            ),
        )
    )

    out.append(("h2", "Terms"))
    out.append(("p", "The terms used in the Conformance Level information are defined as follows:"))
    out.append(("ul", [f"{name}: {meaning}" for name, meaning in text["terms"].items()]))

    out.append(("h2", edition["wcag_heading"]))
    out.append(("p", edition["also_documents"]))
    out.append(("p", "Note: " + edition["wcag_note"]))
    out.append(("p", text["aaa_note"]))
    tables = table_rows(version)
    header = ["Criteria", "Conformance Level", "Remarks and Explanations"]
    for heading, table in tables[:2]:
        out.append(("h3", heading))
        out.append(
            (
                "table",
                (heading, header, [list(row_cells(r, rows.get(r.id), version)) for r in table]),
            )
        )

    out.append(("h2", "Revised Section 508 Report"))
    for heading, table in tables[2:]:
        out.append(("h3", heading))
        out.append(
            (
                "table",
                (heading, header, [list(row_cells(r, rows.get(r.id), version)) for r in table]),
            )
        )
    out.append(("h3", "Chapter 4: Hardware"))
    out.append(("p", text["hardware_note"]))

    disclaimer = (report.get("legal_disclaimer") or "").strip()
    if disclaimer:
        out += [("h2", "Legal Disclaimer"), ("p", disclaimer)]

    issues = [i for i in doc.get("issues", []) if isinstance(i, dict)]
    if issues:
        out.append(("h2", "ACR Issue Detail Supplement"))
        out.append(
            (
                "p",
                "Companion to the ACR in the form described on Section508.gov: severity, the area "
                "impacted and how far it spreads, the impacted user group and the workaround.",
            )
        )
        out.append(
            (
                "table",
                (
                    "Known accessibility issues",
                    SUPPLEMENT_HEADER,
                    [supplement_row(i) for i in issues],
                ),
            )
        )
    if findings.open_items:
        out.append(("h2", "Open items"))
        out.append(
            (
                "p",
                "Remove this section when every item is resolved. It is working information "
                "for the report's authors and is not part of the VPAT.",
            )
        )
        out.append(("ul", list(findings.open_items)))
    return title, out


SUPPLEMENT_HEADER = [
    "Issue",
    "Severity",
    "Area impacted",
    "Impacted user group",
    "Workaround",
    "Criteria",
]


def supplement_row(issue: dict[str, Any]) -> list[str]:
    return [
        f"{issue.get('id', '')}: {issue.get('summary', '')}".strip(": "),
        str(issue.get("severity", "")),
        str(issue.get("area", "")),
        "; ".join(issue.get("impacted_users", [])),
        str(issue.get("workaround", "")),
        ", ".join(issue.get("criteria", [])),
    ]


def md_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", "<br>")


def to_markdown(title: str, blocks_: list[tuple[str, Any]]) -> str:
    lines: list[str] = []
    for kind, payload in blocks_:
        if kind in ("h1", "h2", "h3"):
            lines += [f"{'#' * int(kind[1])} {payload}", ""]
        elif kind == "p":
            lines += [payload, ""]
        elif kind == "note":
            lines += [f"> **{payload}**", ""]
        elif kind == "field":
            label, value = payload
            lines += [f"**{label}:** {value}".rstrip(), ""]
        elif kind == "ul":
            lines += [f"- {item}" for item in payload] + [""]
        elif kind == "table":
            caption, header, rows = payload
            lines.append("| " + " | ".join(header) + " |")
            lines.append("|" + "|".join(["---"] * len(header)) + "|")
            lines += ["| " + " | ".join(md_cell(c) for c in row) + " |" for row in rows]
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


HTML_STYLE = (
    "body{font-family:system-ui,sans-serif;line-height:1.5;max-width:70rem;margin:2rem auto;"
    "padding:0 1rem;color:#1b1b1b}"
    "table{border-collapse:collapse;width:100%;margin:1rem 0}"
    "th,td{border:1px solid #565c65;padding:.5rem;text-align:left;vertical-align:top}"
    "th{background:#dfe1e2}caption{text-align:left;font-weight:bold;padding:.5rem 0}"
    ".draft{border:3px solid #1b1b1b;padding:.75rem;font-weight:bold}"
)


def to_html(title: str, blocks_: list[tuple[str, Any]], lang: str = "en") -> str:
    esc = html.escape
    parts = [
        "<!DOCTYPE html>",
        f'<html lang="{lang}">',
        '<head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{esc(title)}</title><style>{HTML_STYLE}</style></head>",
        "<body><main>",
    ]
    for kind, payload in blocks_:
        if kind in ("h1", "h2", "h3"):
            parts.append(f"<{kind}>{esc(payload)}</{kind}>")
        elif kind == "p":
            parts.append(f"<p>{esc(payload)}</p>")
        elif kind == "note":
            parts.append(f'<p class="draft">{esc(payload)}</p>')
        elif kind == "field":
            label, value = payload
            parts.append(f"<p><strong>{esc(label)}:</strong> {esc(value)}</p>")
        elif kind == "ul":
            parts.append("<ul>" + "".join(f"<li>{esc(i)}</li>" for i in payload) + "</ul>")
        elif kind == "table":
            caption, header, rows = payload
            parts.append(f"<table><caption>{esc(caption)}</caption><thead><tr>")
            parts.append("".join(f'<th scope="col">{esc(h)}</th>' for h in header))
            parts.append("</tr></thead><tbody>")
            for row in rows:
                parts.append("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in row) + "</tr>")
            parts.append("</tbody></table>")
    parts.append("</main></body></html>")
    return "\n".join(parts) + "\n"


def csv_safe(value: object) -> str:
    """Neutralize cells a spreadsheet would run as formulas (OWASP CSV injection guidance)."""
    text = str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def supplement_csv(doc: dict[str, Any]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        [
            "Issue ID",
            "Summary",
            "Severity",
            "Area impacted",
            "Impacted user group",
            "Workaround",
            "Criteria",
        ]
    )
    for issue in doc.get("issues", []):
        writer.writerow(
            csv_safe(cell)
            for cell in (
                issue.get("id", ""),
                issue.get("summary", ""),
                issue.get("severity", ""),
                issue.get("area", ""),
                "; ".join(issue.get("impacted_users", [])),
                issue.get("workaround", ""),
                ", ".join(issue.get("criteria", [])),
            )
        )
    return buffer.getvalue()


# --- check-template ----------------------------------------------------------------------

W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
VERSION_LINE = re.compile(r"Version\s+(\d+\.\d+\w*)")
EDITION_LINE = re.compile(r"^(Revised Section 508|WCAG|International|EN 301 549)\s+Edition$")
WCAG_CELL = re.compile(r"^(\d\.\d+\.\d+)\s+.+?\(Level (A|AA)\b")
SECTION_CELL = re.compile(r"^([356]\d{2}(?:\.\d+)*)\s")


def docx_text(path: Path) -> tuple[list[str], list[str]]:
    """Return (paragraph texts, first-cell texts of every table row) from a .docx file."""
    try:
        with zipfile.ZipFile(path) as archive:
            info = archive.getinfo("word/document.xml")
            if info.file_size > MAX_DOCX_BYTES:
                raise InputError(
                    f"{path}: document.xml is larger than {MAX_DOCX_BYTES} bytes; "
                    "refusing to parse it."
                )
            data = archive.read("word/document.xml")
            # Word files carry no DTD. Refuse one rather than expand entities from a download.
            if b"<!DOCTYPE" in data or b"<!ENTITY" in data:
                raise InputError(
                    f"{path}: document.xml declares a DTD or entity; refusing to parse it."
                )
            root = ET.fromstring(data)
    except (OSError, zipfile.BadZipFile, KeyError, ET.ParseError) as err:
        raise InputError(
            f"cannot read {path} as a Word document: {err}. Download the .docx from itic.org again."
        ) from err

    def text(element: ET.Element) -> str:
        return "".join(t.text or "" for t in element.iter(f"{W_NS}t")).strip()

    paragraphs = [text(p) for p in root.iter(f"{W_NS}p") if text(p)]
    firsts: list[str] = []
    for row in root.iter(f"{W_NS}tr"):
        cells = row.findall(f"{W_NS}tc")
        if cells:
            first = cells[0].find(f"{W_NS}p")
            if first is not None:
                firsts.append(text(first))
    return paragraphs, firsts


def template_ids(path: Path) -> tuple[str, str, set[str], set[str]]:
    """Return (version, edition, WCAG A/AA ids, Section 508 chapter 3/5/6 ids)."""
    paragraphs, firsts = docx_text(path)
    version = next((m[1] for p in paragraphs if (m := VERSION_LINE.search(p))), "unknown")
    edition = next((m[1] for p in paragraphs if (m := EDITION_LINE.match(p))), "unknown")
    wcag = {m[1] for c in firsts if (m := WCAG_CELL.match(c))}
    s508 = {m[1] for c in firsts if (m := SECTION_CELL.match(c))}
    return version, edition, wcag, s508


def bundled_ids(edition: str) -> tuple[set[str], set[str]]:
    criteria = load_criteria()
    limit = "2.0" if edition == "Revised Section 508" else "2.2"
    wcag = {w["id"] for w in criteria["wcag"] if version_key(w["since"]) <= version_key(limit)}
    s508 = {r["id"] for ch in criteria["section508"].values() for r in ch["rows"]}
    return wcag, s508


# --- command line ------------------------------------------------------------------------


def load_evidence(path: str) -> dict[str, Any]:
    data = read_json(Path(path))
    if not isinstance(data, dict):
        raise InputError(f"{path} should hold a JSON object at the top level.")
    return data


def emit(text: str, out: str | None) -> None:
    if out:
        try:
            Path(out).write_text(text, encoding="utf-8")
        except OSError as err:
            raise InputError(
                f"cannot write {out}: {err.strerror}. Check the folder exists."
            ) from err
        print(f"wrote {out}")
    else:
        sys.stdout.write(text)


def cmd_init(args: argparse.Namespace) -> int:
    if args.out and Path(args.out).exists() and not args.force:
        raise InputError(
            f"{args.out} already exists and may hold hand-entered evidence. Choose another path, "
            "or pass --force to overwrite it."
        )
    emit(json.dumps(scaffold(args.wcag, args.web_only), indent=2) + "\n", args.out)
    return 0


def print_findings(findings: Findings) -> None:
    for message in findings.errors:
        print(f"error: {message}", file=sys.stderr)
    for message in findings.warnings:
        print(f"warning: {message}", file=sys.stderr)


def cmd_validate(args: argparse.Namespace) -> int:
    doc = load_evidence(args.evidence)
    findings = validate(doc)
    if args.json:
        print(
            json.dumps(
                {
                    "errors": findings.errors,
                    "warnings": findings.warnings,
                    "open_items": findings.open_items,
                },
                indent=2,
            )
        )
    else:
        print_findings(findings)
        for message in findings.open_items[:OPEN_ITEMS_SHOWN]:
            print(f"open: {message}")
        hidden = len(findings.open_items) - OPEN_ITEMS_SHOWN
        if hidden > 0:
            print(f"open: ... and {hidden} more (run needs-human, or validate --json, for all)")
        print(
            f"{len(findings.errors)} error(s), {len(findings.warnings)} warning(s), "
            f"{len(findings.open_items)} open item(s)"
        )
    return 1 if findings.errors else 0


def cmd_needs_human(args: argparse.Namespace) -> int:
    doc = load_evidence(args.evidence)
    needed = rows_needing_a_person(doc)
    if not needed:
        print("Every row has a check run by a person.")
        return 0
    print("Rows that still need a person (row | status | why | usual check):")
    for info, status, why in needed:
        print(f"{info.id} {info.title} | {status} | {why} | {', '.join(info.hint) or '-'}")
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    doc = load_evidence(args.evidence)
    findings = validate(doc)
    print_findings(findings)
    if findings.errors:
        print(
            f"error: {len(findings.errors)} error(s); fix the evidence file, then render again.",
            file=sys.stderr,
        )
        return 1
    if args.final and findings.open_items:
        print("error: --final was given but the report has open items:", file=sys.stderr)
        for message in findings.open_items:
            print(f"  - {message}", file=sys.stderr)
        return 1
    title, parts = blocks(doc, findings)
    emit(to_html(title, parts) if args.format == "html" else to_markdown(title, parts), args.out)
    return 0


def cmd_supplement(args: argparse.Namespace) -> int:
    doc = load_evidence(args.evidence)
    findings = validate(doc)
    print_findings(findings)
    if findings.errors:
        return 1
    emit(supplement_csv(doc), args.out)
    return 0


def cmd_check_template(args: argparse.Namespace) -> int:
    version, edition, wcag, s508 = template_ids(Path(args.docx))
    print(f"template: edition {edition!r}, version {version!r}")
    if edition == "unknown" or not wcag:
        print(
            "error: this does not look like a VPAT edition file (no edition line or WCAG rows).",
            file=sys.stderr,
        )
        return 2
    bundled_wcag, bundled_508 = bundled_ids(edition)
    bundled_version = load_criteria()["vpat"]["version"]
    differences = 0
    if version != bundled_version:
        print(f"version differs: template {version}, bundled data {bundled_version}")
        differences += 1
    for label, current, bundled in (
        ("WCAG A/AA", wcag, bundled_wcag),
        ("Section 508 chapters 3, 5, 6", s508, bundled_508),
    ):
        if edition == "WCAG" and label.startswith("Section"):
            continue
        for rid in sorted(current - bundled):
            print(f"new in template ({label}): {rid}")
            differences += 1
        for rid in sorted(bundled - current):
            print(f"missing from template ({label}): {rid}")
            differences += 1
    if differences:
        print(
            f"{differences} difference(s). Update data/criteria.json from the template "
            "before relying on this skill."
        )
        return 1
    print("rows match the bundled data")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="write a starter evidence file with every row Not Evaluated")
    init.add_argument(
        "--wcag",
        choices=WCAG_VERSIONS,
        default="2.0",
        help="highest WCAG version to report (2.0 = Revised Section 508 edition)",
    )
    init.add_argument(
        "--web-only", action="store_true", help="pre-fill sections 502, 503, 504 as Not Applicable"
    )
    init.add_argument("--out", help="file to write (default: stdout)")
    init.add_argument("--force", action="store_true", help="overwrite --out if it exists")
    init.set_defaults(run=cmd_init)

    check = sub.add_parser("validate", help="check the evidence file against the rules")
    check.add_argument("evidence")
    check.add_argument("--json", action="store_true")
    check.set_defaults(run=cmd_validate)

    human = sub.add_parser("needs-human", help="list the rows that still need a person's check")
    human.add_argument("evidence")
    human.set_defaults(run=cmd_needs_human)

    render = sub.add_parser("render", help="write the ACR")
    render.add_argument("evidence")
    render.add_argument("--format", choices=("md", "html"), default="md")
    render.add_argument("--out")
    render.add_argument(
        "--final", action="store_true", help="refuse to render while open items remain"
    )
    render.set_defaults(run=cmd_render)

    supplement = sub.add_parser(
        "supplement", help="write the issue list as CSV for the GSA supplement"
    )
    supplement.add_argument("evidence")
    supplement.add_argument("--out")
    supplement.set_defaults(run=cmd_supplement)

    template = sub.add_parser(
        "check-template", help="compare a downloaded VPAT .docx with the bundled rows"
    )
    template.add_argument("docx")
    template.set_defaults(run=cmd_check_template)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.run(args))
    except InputError as err:
        print(f"error: {err}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
