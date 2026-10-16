"""Tests for the section-508-report skill's acr.py, on synthetic fixtures only (no network)."""

from __future__ import annotations

import copy
import csv
import importlib.util
import io
import json
import sys
import zipfile
from pathlib import Path
from typing import Any

import pytest

SKILL = Path(__file__).resolve().parents[2] / "plugins/accessibility/skills/section-508-report"
SPEC = importlib.util.spec_from_file_location("acr", SKILL / "scripts/acr.py")
assert SPEC and SPEC.loader
acr = importlib.util.module_from_spec(SPEC)
sys.modules["acr"] = acr
SPEC.loader.exec_module(acr)

HEADER = {
    "company": "Example Co",
    "product": "Example Permit Portal 2.3",
    "report_date": "October 2026",
    "description": "A web application for permits.",
    "contact": "accessibility@example.com",
    "notes": "",
    "evaluation_methods": "Automated scan, then keyboard and screen-reader testing.",
    "vpat_version": "2.5Rev",
    "legal_disclaimer": "",
    "product_has_hardware": False,
}
SESSIONS = [
    {
        "id": "scan",
        "method": "automated",
        "by": "tool",
        "tool": "Rule engine",
        "date": "2026-10-12",
    },
    {
        "id": "kbd",
        "method": "keyboard",
        "by": "human",
        "tester": "QA engineer",
        "date": "2026-10-13",
        "scope": "main flows",
    },
    {"id": "bot", "method": "code-review", "by": "assistant", "date": "2026-10-13"},
]


def doc_with(rows: dict[str, Any], version: str = "2.0", **extra: Any) -> dict[str, Any]:
    return {
        "report": copy.deepcopy(HEADER),
        "wcag_version": version,
        "sessions": copy.deepcopy(SESSIONS),
        "rows": rows,
        "issues": [],
        **extra,
    }


def supports(session: str = "kbd") -> dict[str, Any]:
    return {
        "status": "Supports",
        "remarks": "",
        "evidence": [{"session": session, "result": "pass"}],
    }


def complete_doc(version: str = "2.0") -> dict[str, Any]:
    """Every answerable row Supports with a human pass, so nothing is left open."""
    rows = {rid: supports() for rid in acr.answerable_rows(version)}
    return doc_with(rows, version)


def errors_for(doc: dict[str, Any]) -> list[str]:
    return acr.validate(doc).errors


# --- data --------------------------------------------------------------------------------


def test_wcag_rows_are_level_a_or_aa_and_unique() -> None:
    wcag = acr.load_criteria()["wcag"]
    ids = [w["id"] for w in wcag]
    assert len(ids) == len(set(ids))
    assert {w["level"] for w in wcag} == {"A", "AA"}


def test_version_filter_adds_criteria_without_removing_any() -> None:
    v20, v21, v22 = (set(acr.answerable_rows(v)) for v in ("2.0", "2.1", "2.2"))
    assert v20 < v21 < v22
    assert "2.4.11" in v22 - v21
    assert "1.4.10" in v21 - v20
    assert "1.1.1" in v20


def test_template_answers_4_1_1_and_headings_are_not_answerable() -> None:
    rows = acr.answerable_rows("2.2")
    assert "4.1.1" not in rows
    for ref in ("501.1", "504.2", "602.3", "502", "503.4", "601.1"):
        assert ref not in rows
    assert {"302.1", "302.9", "502.3.14", "603.3"} <= set(rows)


def test_chapter_4_hardware_rows_are_not_in_the_data() -> None:
    ids = {r["id"] for ch in acr.load_criteria()["section508"].values() for r in ch["rows"]}
    assert not any(i.startswith("4") for i in ids)


# --- validate: rows ----------------------------------------------------------------------


def test_supports_needs_a_passing_check_run_by_a_person() -> None:
    for session in ("scan", "bot"):
        errors = errors_for(doc_with({"2.1.1": supports(session)}))
        assert any("2.1.1 Keyboard" in e and "run by a person" in e for e in errors), session
    assert errors_for(doc_with({"2.1.1": supports("kbd")})) == []


def test_supports_with_a_failing_result_is_refused() -> None:
    row = supports()
    row["evidence"].append({"session": "scan", "result": "fail"})
    assert any("failing result" in e for e in errors_for(doc_with({"2.1.1": row})))


def test_partial_and_does_not_support_need_remarks_and_a_failing_result() -> None:
    row = {
        "status": "Partially Supports",
        "remarks": "",
        "evidence": [{"session": "scan", "result": "pass"}],
    }
    errors = errors_for(doc_with({"1.4.3": row}))
    assert any("without remarks" in e for e in errors)
    assert any("without a failing result" in e for e in errors)
    good = {
        "status": "Does Not Support",
        "remarks": "Secondary text is 3.2:1 on most pages.",
        "evidence": [{"session": "scan", "result": "fail"}],
    }
    assert errors_for(doc_with({"1.4.3": good})) == []


def test_not_applicable_needs_a_reason_and_warns_on_wcag_rows() -> None:
    assert any(
        "without remarks" in e
        for e in errors_for(
            doc_with({"1.2.4": {"status": "Not Applicable", "remarks": "", "evidence": []}})
        )
    )
    findings = acr.validate(
        doc_with(
            {"1.2.4": {"status": "Not Applicable", "remarks": "No live media.", "evidence": []}}
        )
    )
    assert any("Not Applicable on a WCAG row" in w for w in findings.warnings)
    chapter = acr.validate(
        doc_with({"502.4": {"status": "Not Applicable", "remarks": "Web only.", "evidence": []}})
    )
    assert not any("Not Applicable on a WCAG row" in w for w in chapter.warnings)


def test_not_evaluated_is_an_open_item_and_one_aggregated_warning() -> None:
    findings = acr.validate(doc_with({}))
    assert findings.errors == []
    assert sum("read Not Evaluated" in w for w in findings.warnings) == 1
    assert any(i.startswith("1.1.1 Non-text Content: no row") for i in findings.open_items)


def test_unknown_row_ids_are_refused_with_the_reason() -> None:
    errors = errors_for(doc_with({"9.9.9": supports(), "4.1.1": supports(), "2.4.11": supports()}))
    assert len(errors) == 3
    assert all("not an answerable row" in e for e in errors)
    # A criterion added after the chosen WCAG version is outside the report.
    assert errors_for(doc_with({"2.4.11": supports()}, version="2.2")) == []


def test_bad_status_result_and_evidence_references() -> None:
    bad_status = {"status": "Mostly", "remarks": "", "evidence": []}
    assert any('"status" must be one of' in e for e in errors_for(doc_with({"2.1.1": bad_status})))
    bad_result = {
        "status": "Supports",
        "remarks": "",
        "evidence": [{"session": "kbd", "result": "ok"}],
    }
    assert any('"result" must be one of' in e for e in errors_for(doc_with({"2.1.1": bad_result})))
    dangling = {
        "status": "Supports",
        "remarks": "",
        "evidence": [{"session": "nope", "result": "pass"}],
    }
    assert any("session 'nope'" in e for e in errors_for(doc_with({"2.1.1": dangling})))


# --- validate: header, sessions, issues --------------------------------------------------


def test_blank_and_placeholder_header_fields_become_open_items() -> None:
    doc = doc_with({})
    doc["report"]["company"] = ""
    doc["report"]["contact"] = "TODO"
    doc["report"]["product"] = "[Product name]"
    items = acr.validate(doc).open_items
    for name in ("company", "contact", "product"):
        assert any(f'"{name}"' in i for i in items), name


def test_vpat_version_mismatch_warns_and_hardware_is_refused() -> None:
    doc = doc_with({})
    doc["report"]["vpat_version"] = "9.9"
    doc["report"]["product_has_hardware"] = True
    findings = acr.validate(doc)
    assert any("verified against 2.5Rev" in w for w in findings.warnings)
    assert any("Chapter 4" in e for e in findings.errors)


def test_session_rules() -> None:
    doc = doc_with({})
    doc["sessions"] = [
        {"id": "a", "method": "keyboard", "by": "human", "date": "2026-10-01"},
        {"id": "b", "method": "automated", "by": "tool", "date": "2026-10-01"},
        {"id": "c", "method": "telepathy", "by": "human", "tester": "x", "date": "2026-10-01"},
        {"id": "c", "method": "keyboard", "by": "robot", "date": "2026-10-01"},
        {"method": "keyboard", "by": "human"},
    ]
    errors = errors_for(doc)
    assert any('session "a"' in e and 'names no "tester"' in e for e in errors)
    assert any('session "b"' in e and 'names no "tool"' in e for e in errors)
    assert any('"method" must be one of' in e for e in errors)
    assert any("defined twice" in e for e in errors)
    assert any('"by" must be one of' in e for e in errors)
    assert any('has no "id"' in e for e in errors)


def test_no_sessions_and_no_methods_text_is_an_open_item() -> None:
    doc = doc_with({})
    doc["sessions"] = []
    doc["report"]["evaluation_methods"] = ""
    assert any("evaluation methods" in i for i in acr.validate(doc).open_items)


def issue(**changes: Any) -> dict[str, Any]:
    base = {
        "id": "A11Y-1",
        "summary": "Icon buttons have no names",
        "criteria": ["1.1.1"],
        "severity": "Major Accessibility Issue",
        "area": "Payment page",
        "impacted_users": ["Without Vision"],
        "workaround": "None known",
    }
    return {**base, **changes}


def test_issue_rules() -> None:
    doc = doc_with({}, issues=[issue()])
    assert errors_for(doc) == []
    bad = doc_with(
        {},
        issues=[
            issue(
                severity="Big",
                impacted_users=["Everyone"],
                criteria=["9.9.9"],
                area="",
                workaround="",
            ),
            issue(id="A11Y-1", summary=""),
        ],
    )
    errors = errors_for(bad)
    for needle in (
        '"severity"',
        '"impacted_users"',
        "'9.9.9'",
        '"area"',
        '"workaround"',
        "defined twice",
        '"summary"',
    ):
        assert any(needle in e for e in errors), needle


def test_partial_row_without_an_issue_warns_only_when_issues_are_used() -> None:
    row = {
        "status": "Partially Supports",
        "remarks": "Three buttons have no names.",
        "evidence": [{"session": "scan", "result": "fail"}],
    }
    assert not any("issues" in w for w in acr.validate(doc_with({"1.1.1": row})).warnings)
    covered = acr.validate(doc_with({"1.1.1": row}, issues=[issue()]))
    assert not any('no entry in "issues"' in w for w in covered.warnings)
    other = acr.validate(doc_with({"1.1.1": row}, issues=[issue(criteria=["1.4.3"])]))
    assert any('no entry in "issues"' in w for w in other.warnings)


# --- init and needs-human ----------------------------------------------------------------


def test_init_scaffold_validates_and_web_only_prefills_502_503_504() -> None:
    plain = acr.scaffold("2.0", web_only=False)
    assert acr.validate(plain).errors == []
    assert all(r["status"] == "Not Evaluated" for r in plain["rows"].values())
    web = acr.scaffold("2.0", web_only=True)
    assert acr.validate(web).errors == []
    prefilled = {rid for rid, r in web["rows"].items() if r.get("prefilled")}
    assert {"502.2.1", "503.4.2", "504.4"} <= prefilled
    assert "602.2" not in prefilled
    assert sum("pre-filled" in i for i in acr.validate(web).open_items) == 1


def test_needs_human_lists_what_a_person_still_has_to_check() -> None:
    rows = {
        "2.1.1": supports("kbd"),
        "2.1.2": supports("scan") | {"status": "Partially Supports", "remarks": "x"},
        "1.4.3": {
            "status": "Does Not Support",
            "remarks": "Fails.",
            "evidence": [{"session": "scan", "result": "fail"}],
        },
        "1.2.4": {"status": "Not Applicable", "remarks": "No live media.", "evidence": []},
        "502.4": {"status": "Not Applicable", "remarks": "Web.", "evidence": [], "prefilled": True},
    }
    needed = {info.id: why for info, _, why in acr.rows_needing_a_person(doc_with(rows))}
    assert "2.1.1" not in needed  # a person passed it
    assert needed["2.1.2"] == "no check run by a person"
    assert "1.4.3" not in needed  # a recorded failure needs no tester
    assert "1.2.4" not in needed
    assert needed["502.4"] == "confirm the pre-filled answer"
    assert needed["1.1.1"] == "not evaluated"


# --- render ------------------------------------------------------------------------------


def render(doc: dict[str, Any], fmt: str = "md") -> str:
    findings = acr.validate(doc)
    title, blocks = acr.blocks(doc, findings)
    return acr.to_html(title, blocks) if fmt == "html" else acr.to_markdown(title, blocks)


def test_complete_report_has_no_draft_banner_or_open_items() -> None:
    doc = complete_doc()
    assert acr.validate(doc).open_items == []
    md = render(doc)
    assert "DRAFT" not in md
    assert "## Open items" not in md


def test_508_edition_layout() -> None:
    md = render(complete_doc("2.0"))
    assert "Revised Section 508 Edition" in md
    assert "(Based on VPAT® Version 2.5Rev)" in md
    assert "## WCAG 2.0 Report" in md
    assert "### Table 1: Success Criteria, Level A" in md
    assert "### Table 2: Success Criteria, Level AA" in md
    assert "### Chapter 3: Functional Performance Criteria (FPC)" in md
    assert "### Chapter 5: Software" in md
    assert "### Chapter 6: Support Documentation and Services" in md
    assert "### Chapter 4: Hardware" in md
    # 4.1.1 is answered by the template, and AAA rows are absent.
    assert "| 4.1.1 Parsing (Level A) | Supports | For WCAG 2.0 and the 508 standards" in md
    assert "Contrast (Enhanced)" not in md
    assert "EN 301 549" not in md.split("## Terms")[0]


def test_wcag_2_2_report_uses_the_international_layout_without_en_301_549() -> None:
    md = render(complete_doc("2.2"))
    assert "International Edition" in md
    assert "## WCAG 2.x Report" in md
    assert "Web Content Accessibility Guidelines 2.1" in md
    assert "Web Content Accessibility Guidelines 2.2" in md
    assert "| EN 301 549" in md and "| (No) |" in md
    assert "2.4.11 Focus Not Obscured (Minimum) (Level AA, WCAG 2.2 only)" in md
    assert "1.4.10 Reflow (Level AA, WCAG 2.1 and 2.2)" in md
    assert "WCAG 2.0, 2.1, EN 301 549, and Revised 508 Standards" in md


def test_draft_banner_and_open_items_section() -> None:
    md = render(doc_with({}))
    assert "> **DRAFT. Not ready to publish:" in md
    assert "## Open items" in md
    assert "| Web: Not Evaluated | Web: Not evaluated. A person needs to run this check" in md


def test_markdown_cells_are_escaped() -> None:
    row = {
        "status": "Does Not Support",
        "remarks": "Pipes | and\nnewlines break tables.",
        "evidence": [{"session": "scan", "result": "fail"}],
    }
    md = render(doc_with({"1.4.3": row}))
    assert "Pipes \\| and<br>newlines break tables." in md


def test_html_is_a_structured_accessible_document() -> None:
    row = {
        "status": "Does Not Support",
        "remarks": "<script>alert(1)</script> & more",
        "evidence": [{"session": "scan", "result": "fail"}],
    }
    out = render(doc_with({"1.4.3": row}), "html")
    assert out.startswith("<!DOCTYPE html>")
    assert '<html lang="en">' in out
    assert "<title>Example Co Accessibility Conformance Report</title>" in out
    assert '<th scope="col">Criteria</th>' in out
    assert "<caption>Table 1: Success Criteria, Level A</caption>" in out
    assert "<script>" not in out
    assert "&lt;script&gt;alert(1)&lt;/script&gt; &amp; more" in out
    assert out.count("<h1>") == 1


def test_supplement_section_and_csv() -> None:
    doc = doc_with({}, issues=[issue(summary="Names, missing")])
    md = render(doc)
    assert "## ACR Issue Detail Supplement" in md
    rows = list(csv.reader(io.StringIO(acr.supplement_csv(doc))))
    assert rows[0][:3] == ["Issue ID", "Summary", "Severity"]
    assert rows[1][1] == "Names, missing"
    assert rows[1][4] == "Without Vision"


def test_legal_disclaimer_appears_only_when_given() -> None:
    doc = complete_doc()
    assert "Legal Disclaimer" not in render(doc)
    doc["report"]["legal_disclaimer"] = "For information only."
    assert "## Legal Disclaimer" in render(doc)


# --- command line ------------------------------------------------------------------------


def write(tmp_path: Path, doc: dict[str, Any], name: str = "evidence.json") -> str:
    path = tmp_path / name
    path.write_text(json.dumps(doc))
    return str(path)


def test_cli_render_refuses_errors_and_final_refuses_open_items(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = write(tmp_path, doc_with({"2.1.1": supports("scan")}))
    assert acr.main(["render", bad]) == 1
    assert "run by a person" in capsys.readouterr().err
    draft = write(tmp_path, doc_with({}), "draft.json")
    assert acr.main(["render", draft, "--final"]) == 1
    assert "open items" in capsys.readouterr().err
    assert acr.main(["render", draft]) == 0


def test_cli_render_final_succeeds_on_a_complete_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    complete = write(tmp_path, complete_doc())
    out = tmp_path / "acr.html"
    assert acr.main(["render", complete, "--final", "--format", "html", "--out", str(out)]) == 0
    assert out.read_text().startswith("<!DOCTYPE html>")
    assert "wrote" in capsys.readouterr().out


def test_cli_validate_exit_codes_and_missing_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert acr.main(["validate", write(tmp_path, doc_with({}))]) == 0
    assert (
        acr.main(["validate", write(tmp_path, doc_with({"2.1.1": supports("bot")}), "b.json")]) == 1
    )
    capsys.readouterr()
    assert acr.main(["validate", str(tmp_path / "missing.json")]) == 2
    assert "missing.json" in capsys.readouterr().err
    broken = tmp_path / "broken.json"
    broken.write_text("{not json")
    assert acr.main(["validate", str(broken)]) == 2
    assert "not valid JSON" in capsys.readouterr().err


def test_cli_validate_json_and_top_level_type(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert acr.main(["validate", write(tmp_path, doc_with({})), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert set(report) == {"errors", "warnings", "open_items"}
    listing = tmp_path / "list.json"
    listing.write_text("[]")
    assert acr.main(["validate", str(listing)]) == 2


def test_cli_init_writes_a_starter_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "start.json"
    assert acr.main(["init", "--wcag", "2.1", "--web-only", "--out", str(out)]) == 0
    doc = json.loads(out.read_text())
    assert doc["wcag_version"] == "2.1"
    assert "1.4.10" in doc["rows"]
    assert "2.4.11" not in doc["rows"]
    assert acr.main(["needs-human", str(out)]) == 0
    assert "confirm the pre-filled answer" in capsys.readouterr().out


def test_bundled_example_validates_and_renders() -> None:
    example = json.loads((SKILL / "templates/evidence.example.json").read_text())
    findings = acr.validate(example)
    assert findings.errors == []
    assert render(example).startswith("# Example Co Accessibility Conformance Report")


# --- check-template ----------------------------------------------------------------------


def make_docx(
    path: Path, *, edition: str, version: str, drop: str | None = None, extra: str | None = None
) -> Path:
    criteria = acr.load_criteria()
    limit = "2.0" if edition == "Revised Section 508" else "2.2"
    cells: list[str] = []
    for w in criteria["wcag"]:
        if acr.version_key(w["since"]) <= acr.version_key(limit):
            cells.append(f"{w['id']} {w['title']} (Level {w['level']})")
    if edition != "WCAG":
        for chapter in criteria["section508"].values():
            cells += [f"{r['id']} {r['title']}" for r in chapter["rows"]]
    cells = [c for c in cells if not (drop and c.startswith(drop + " "))]
    if extra:
        cells.append(extra)
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

    def para(text: str) -> str:
        return f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>"

    body = para(f"{edition} Edition") + para(f"(Based on VPAT® Version {version})")
    body += "<w:tbl>" + "".join(f"<w:tr><w:tc>{para(c)}</w:tc></w:tr>" for c in cells) + "</w:tbl>"
    xml = f'<?xml version="1.0"?><w:document xmlns:w="{ns}"><w:body>{body}</w:body></w:document>'
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", xml)
    return path


@pytest.mark.parametrize("edition", ["Revised Section 508", "WCAG", "International"])
def test_check_template_passes_when_rows_match(
    tmp_path: Path, edition: str, capsys: pytest.CaptureFixture[str]
) -> None:
    path = make_docx(tmp_path / "v.docx", edition=edition, version="2.5Rev")
    assert acr.main(["check-template", str(path)]) == 0
    assert "rows match" in capsys.readouterr().out


def test_check_template_reports_missing_new_and_version_drift(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = make_docx(
        tmp_path / "v.docx",
        edition="Revised Section 508",
        version="2.6",
        drop="2.1.1",
        extra="2.9.9 Invented Criterion (Level AA)",
    )
    assert acr.main(["check-template", str(path)]) == 1
    out = capsys.readouterr().out
    assert "version differs: template 2.6" in out
    assert "missing from template (WCAG A/AA): 2.1.1" in out
    assert "new in template (WCAG A/AA): 2.9.9" in out


def test_check_template_rejects_files_that_are_not_vpat_editions(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "x.docx"
    bad.write_text("not a zip")
    assert acr.main(["check-template", str(bad)]) == 2
    assert "Word document" in capsys.readouterr().err
    empty = tmp_path / "empty.docx"
    with zipfile.ZipFile(empty, "w") as archive:
        archive.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body/></w:document>',
        )
    assert acr.main(["check-template", str(empty)]) == 2
    assert "does not look like a VPAT" in capsys.readouterr().err


# --- hardening ---------------------------------------------------------------------------


def test_supports_backed_by_an_unrelated_kind_of_check_warns() -> None:
    row = supports("kbd") | {"remarks": "Works."}
    keyboard_ok = acr.validate(doc_with({"2.1.1": row}))
    assert not any("usually settled by" in w for w in keyboard_ok.warnings)
    # 1.1.1 is usually settled by content or screen-reader checks, not a keyboard session.
    mismatch = acr.validate(doc_with({"1.1.1": row}))
    assert any("usually settled by content, screen-reader" in w for w in mismatch.warnings)


def test_init_will_not_overwrite_hand_entered_evidence(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "evidence.json"
    out.write_text('{"hand": "entered"}')
    assert acr.main(["init", "--out", str(out)]) == 2
    assert "already exists" in capsys.readouterr().err
    assert json.loads(out.read_text()) == {"hand": "entered"}
    assert acr.main(["init", "--out", str(out), "--force"]) == 0
    assert "rows" in json.loads(out.read_text())


def test_unwritable_output_is_a_clean_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    evidence = write(tmp_path, doc_with({}))
    missing_folder = tmp_path / "nope" / "acr.md"
    assert acr.main(["render", evidence, "--out", str(missing_folder)]) == 2
    assert "cannot write" in capsys.readouterr().err


def test_supplement_csv_neutralizes_formulas() -> None:
    doc = doc_with({}, issues=[issue(summary='=HYPERLINK("http://x")', workaround="-1+1")])
    rows = list(csv.reader(io.StringIO(acr.supplement_csv(doc))))
    assert rows[1][1].startswith("'=")
    assert rows[1][5] == "'-1+1"


def test_check_template_refuses_a_document_with_a_dtd(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hostile = tmp_path / "hostile.docx"
    xml = (
        '<?xml version="1.0"?><!DOCTYPE d [<!ENTITY a "aaaa">]>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body><w:p><w:r><w:t>&a;</w:t></w:r></w:p></w:body></w:document>"
    )
    with zipfile.ZipFile(hostile, "w") as archive:
        archive.writestr("word/document.xml", xml)
    assert acr.main(["check-template", str(hostile)]) == 2
    assert "refusing to parse" in capsys.readouterr().err


def test_evaluation_methods_list_names_who_ran_each_session() -> None:
    md = render(doc_with({}))
    assert "automated (tool: Rule engine), 2026-10-12" in md
    assert "keyboard (human: QA engineer), 2026-10-13: main flows" in md
    assert "code-review (assistant: AI assistant), 2026-10-13" in md
