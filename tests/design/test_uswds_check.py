"""Tests for the uswds skill's uswds_check.py, on synthetic fixtures only (no network)."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "plugins/design/skills/uswds/scripts/uswds_check.py"
SPEC = importlib.util.spec_from_file_location("uswds_check", SCRIPT)
assert SPEC and SPEC.loader
uswds_check = importlib.util.module_from_spec(SPEC)
sys.modules["uswds_check"] = uswds_check
SPEC.loader.exec_module(uswds_check)

# A tiny stand-in for dist/css/uswds.css: a comment, BEM classes, a responsive utility with a
# CSS escape, and a class that only appears inside a comment (which must not count).
CSS = r"""
/* .usa-ghost-class lives only in a comment */
.usa-button { color: red; }
.usa-button--secondary:hover { color: blue; }
.usa-banner__header, .usa-skipnav { display: block; }
.tablet\:grid-col-6 { width: 50%; }
.margin-top-2 { margin-top: 1rem; }
"""

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="Apply for a permit online.">
<title>Apply for a permit</title>
<script src="/assets/uswds/js/uswds-init.min.js"></script>
</head>
<body>
<a class="usa-skipnav" href="#main">Skip to main content</a>
<section class="usa-banner" aria-label="Official website of the United States government"></section>
<main id="main"></main>
<script src="/assets/uswds/js/uswds.min.js"></script>
</body>
</html>
"""


@pytest.fixture
def css(tmp_path: Path) -> Path:
    path = tmp_path / "uswds.css"
    path.write_text(CSS)
    return path


def run(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    code = uswds_check.main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# --- css_classes -------------------------------------------------------------------------


def test_css_classes_unescapes_and_ignores_comments(css: Path) -> None:
    found = uswds_check.css_classes(css)
    assert "usa-button--secondary" in found
    assert "tablet:grid-col-6" in found
    assert "usa-ghost-class" not in found


def test_css_without_usa_classes_is_refused(tmp_path: Path) -> None:
    other = tmp_path / "site.css"
    other.write_text(".card { margin: 0; }")
    with pytest.raises(uswds_check.CheckError, match="defines no usa- classes"):
        uswds_check.css_classes(other)


def test_missing_css_names_the_file(tmp_path: Path) -> None:
    with pytest.raises(uswds_check.CheckError, match="uswds.css"):
        uswds_check.css_classes(tmp_path / "uswds.css")


# --- classes -----------------------------------------------------------------------------


def test_typo_is_reported_with_line_and_suggestion(
    tmp_path: Path, css: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    page = tmp_path / "index.html"
    page.write_text('<p>x</p>\n<button class="usa-button usa-buton--secondary">Go</button>\n')
    code, out, _ = run(["classes", "--css", str(css), str(page)], capsys)
    assert code == 1
    assert f"{page}:2:" in out
    assert 'class "usa-buton--secondary"' in out
    assert 'did you mean "usa-button--secondary"' in out


def test_known_classes_and_other_prefixes_pass(
    tmp_path: Path, css: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    page = tmp_path / "ok.html"
    page.write_text('<div class="usa-button my-own-class margin-top-2 tablet:grid-col-6"></div>')
    code, out, _ = run(["classes", "--css", str(css), str(page)], capsys)
    assert code == 0
    assert "0 unknown class reference(s)" in out


def test_dynamic_tokens_are_skipped(
    tmp_path: Path, css: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    page = tmp_path / "t.html"
    page.write_text(
        '<div class="usa-{{ kind }} usa-${size} usa-button"></div>\n'
        '<div class="<%= cls %> usa-button"></div>\n'
    )
    code, _, _ = run(["classes", "--css", str(css), str(page)], capsys)
    assert code == 0


def test_jsx_class_name_forms_are_read(
    tmp_path: Path, css: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    page = tmp_path / "App.jsx"
    page.write_text(
        'export const A = () => <div className="usa-nope">a</div>;\n'
        "export const B = () => <div className={`usa-button usa-alsonope`}>b</div>;\n"
    )
    code, out, _ = run(["classes", "--css", str(css), "--json", str(page)], capsys)
    assert code == 1
    names = {item["class"] for item in json.loads(out)["unknown_classes"]}
    assert names == {"usa-nope", "usa-alsonope"}


def test_extra_prefix_checks_utilities_and_ignore_skips(
    tmp_path: Path, css: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    page = tmp_path / "u.html"
    page.write_text('<div class="margin-top-2 margin-top-99 usa-js-only"></div>')
    code, out, _ = run(
        ["classes", "--css", str(css), "--prefix", "^margin-", "--ignore", "99$", str(page)],
        capsys,
    )
    assert code == 0, out
    code, out, _ = run(["classes", "--css", str(css), "--prefix", "^margin-", str(page)], capsys)
    assert code == 1
    assert "margin-top-99" in out


def test_folder_scan_skips_node_modules(
    tmp_path: Path, css: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src/a.html").write_text('<div class="usa-bad"></div>')
    (tmp_path / "node_modules/pkg").mkdir(parents=True)
    (tmp_path / "node_modules/pkg/b.html").write_text('<div class="usa-worse"></div>')
    code, out, _ = run(["classes", "--css", str(css), str(tmp_path)], capsys)
    assert code == 1
    assert "usa-bad" in out
    assert "usa-worse" not in out


def test_missing_path_exits_2_with_the_path(
    tmp_path: Path, css: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _, err = run(["classes", "--css", str(css), str(tmp_path / "nope")], capsys)
    assert code == 2
    assert "nope" in err


# --- page --------------------------------------------------------------------------------


def test_page_facts_for_a_complete_document() -> None:
    facts = uswds_check.page_facts(PAGE)
    assert all(facts.values()), facts


def test_page_facts_flag_what_is_missing() -> None:
    bare = (
        "<html><head><title> </title></head>"
        "<body><script src='uswds-init.js'></script></body></html>"
    )
    facts = uswds_check.page_facts(bare)
    assert facts["html lang attribute"] is False
    assert facts["non-empty title"] is False
    assert facts["viewport meta"] is False
    assert facts["meta description"] is False
    assert facts["official banner (usa-banner)"] is False
    assert facts["uswds-init script"] is True
    # The initializer must not be mistaken for the library script.
    assert facts["uswds script"] is False


def test_xml_lang_alone_is_not_an_html_lang() -> None:
    facts = uswds_check.page_facts('<html xml:lang="en"><title>t</title></html>')
    assert facts["html lang attribute"] is False


def test_page_command_marks_partials(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "full.html").write_text(PAGE)
    (tmp_path / "partial.html").write_text('<div class="usa-card"></div>')
    code, out, _ = run(["page", str(tmp_path)], capsys)
    assert code == 0
    assert "present  official banner (usa-banner)" in out
    assert "no <html> element" in out


# --- version -----------------------------------------------------------------------------


def make_project(root: Path, *, installed: str | None, spec: str | None) -> None:
    if spec is not None:
        (root / "package.json").write_text(json.dumps({"dependencies": {"@uswds/uswds": spec}}))
    if installed is not None:
        package_dir = root / "node_modules/@uswds/uswds"
        package_dir.mkdir(parents=True)
        (package_dir / "package.json").write_text(json.dumps({"version": installed}))


def test_up_to_date_with_exact_pin(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    make_project(tmp_path, installed="3.14.0", spec="3.14.0")
    code, out, _ = run(["version", "--project", str(tmp_path), "--latest", "3.14.0"], capsys)
    assert code == 0
    assert "status: up to date" in out
    assert "declares a range" not in out


def test_minor_behind_and_range_note(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    make_project(tmp_path, installed="3.12.1", spec="^3.12.1")
    code, out, _ = run(["version", "--project", str(tmp_path), "--latest", "3.14.0"], capsys)
    assert code == 1
    assert "status: behind" in out
    assert "declares a range" in out


def test_major_behind_points_to_migration_guide(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    make_project(tmp_path, installed="2.14.0", spec="2.14.0")
    code, out, _ = run(["version", "--project", str(tmp_path), "--latest", "3.14.0"], capsys)
    assert code == 1
    assert "major version behind" in out
    assert uswds_check.MIGRATION_URL in out


def test_installed_version_falls_back_to_lockfile(tmp_path: Path) -> None:
    (tmp_path / "package-lock.json").write_text(
        json.dumps({"packages": {"node_modules/@uswds/uswds": {"version": "3.13.0"}}})
    )
    assert uswds_check.installed_version(tmp_path) == ("3.13.0", "package-lock.json")


def test_not_installed_says_how_to_install(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, _ = run(["version", "--project", str(tmp_path), "--latest", "3.14.0"], capsys)
    assert code == 1
    assert "installed: not found" in out
    assert "npm install @uswds/uswds --save-exact" in out


def test_broken_package_json_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "package.json").write_text("{not json")
    code, _, err = run(["version", "--project", str(tmp_path), "--latest", "3.14.0"], capsys)
    assert code == 2
    assert "package.json" in err


def test_registry_failure_refuses_instead_of_guessing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    make_project(tmp_path, installed="3.14.0", spec="3.14.0")

    def offline(*_args: object, **_kwargs: object) -> None:
        raise urllib.error.URLError("no route")

    monkeypatch.setattr(uswds_check.urllib.request, "urlopen", offline)
    code, _, err = run(["version", "--project", str(tmp_path)], capsys)
    assert code == 2
    assert "--latest" in err


def test_registry_answer_is_used_when_no_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    make_project(tmp_path, installed="3.14.0", spec="3.14.0")

    class Answer(io.BytesIO):
        def __enter__(self) -> Answer:
            return self

        def __exit__(self, *_exc: object) -> None:
            self.close()

    monkeypatch.setattr(
        uswds_check.urllib.request,
        "urlopen",
        lambda *_a, **_k: Answer(json.dumps({"version": "3.15.0"}).encode()),
    )
    code, out, _ = run(["version", "--project", str(tmp_path)], capsys)
    assert code == 1
    assert "latest on npm: 3.15.0" in out


def test_folder_scan_prunes_skipped_folders_without_descending(tmp_path: Path) -> None:
    visited = tmp_path / "node_modules" / "deep" / "deeper"
    visited.mkdir(parents=True)
    (visited / "x.html").write_text('<div class="usa-nope"></div>')
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "a.html").write_text("<p></p>")
    (tmp_path / "pages" / "notes.txt").write_text("ignored")
    found = [p.name for p in uswds_check.iter_template_files([tmp_path])]
    assert found == ["a.html"]
