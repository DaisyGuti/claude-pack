"""Tests for scripts/doc_tool.py: folder detection, numbering, supersede edits and checks."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "plugins/team-comms/scripts/doc_tool.py"
TODAY = "2026-10-16"

NYGARD = """# 1. Use DynamoDB

Date: 2025-01-02

## Status

Accepted

## Context

We needed a key-value store.
"""

MADR_OLD = """---
status: "accepted"
date: 2025-03-04
---

# Use Redis for sessions

## Context and Problem Statement

Sessions need a fast store.
"""


@pytest.fixture
def tool(load_script):
    return load_script("doc_tool")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path


def write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# ---------------------------------------------------------------- helpers


@pytest.mark.parametrize(
    ("title", "slug"),
    [
        ("Rate limiting for the public API", "rate-limiting-for-the-public-api"),
        ("  Use Postgres!  ", "use-postgres"),
        ("A" * 80 + " tail words here", "a" * 80),
    ],
)
def test_slugify(tool, title: str, slug: str) -> None:
    result = tool.slugify(title)
    assert result == slug[: tool.SLUG_MAX] or len(result) <= tool.SLUG_MAX
    assert result == result.strip("-")


def test_slugify_cuts_at_a_word_boundary(tool) -> None:
    result = tool.slugify("one two three four five six seven eight nine ten eleven twelve")
    assert len(result) <= tool.SLUG_MAX
    assert not result.endswith("-")
    assert "-".join(result.split("-")) in "one-two-three-four-five-six-seven-eight-nine-ten-eleven"


def test_slugify_refuses_a_title_with_no_letters(tool) -> None:
    with pytest.raises(tool.InputError, match="file name"):
        tool.slugify("!!!")


# ---------------------------------------------------------------- design docs


def test_design_locate_defaults_when_no_folder_exists(tool, root: Path) -> None:
    info = tool.design_locate(root)
    assert info["dir"] == "docs/design"
    assert info["exists"] is False
    assert info["numbered"] is False


def test_design_locate_prefers_an_existing_folder(tool, root: Path) -> None:
    write(root, "docs/rfcs/0007-caching.md", "# x")
    info = tool.design_locate(root)
    assert info["dir"] == "docs/rfcs"
    assert info["numbered"] is True
    assert info["next_number"] == 8
    assert info["number_width"] == 4


def test_design_new_creates_the_folder_and_an_unnumbered_file(tool, root: Path) -> None:
    result = tool.design_new(root, "Rate limiting for the public API", TODAY)
    assert result["path"] == "docs/design/rate-limiting-for-the-public-api.md"
    text = (root / result["path"]).read_text()
    assert "# Rate limiting for the public API" in text
    assert TODAY in text
    assert "{{" not in text


def test_design_new_continues_the_numbering(tool, root: Path) -> None:
    write(root, "docs/rfcs/0001-first.md", "# x")
    result = tool.design_new(root, "Second proposal", TODAY)
    assert result["path"] == "docs/rfcs/0002-second-proposal.md"


def test_design_new_refuses_to_overwrite(tool, root: Path) -> None:
    tool.design_new(root, "Same title", TODAY)
    with pytest.raises(tool.InputError, match="already exists"):
        tool.design_new(root, "Same title", TODAY)


def test_fresh_skeleton_fails_the_check_only_on_placeholders(tool, root: Path) -> None:
    path = root / tool.design_new(root, "Skeleton", TODAY)["path"]
    problems = tool.design_problems(path.read_text())
    assert problems
    assert all("placeholder" in p for p in problems)


def filled_design(tool, root: Path) -> str:
    """The skeleton with every placeholder replaced by plain text."""
    path = root / tool.design_new(root, "Filled", TODAY)["path"]
    return tool.PLACEHOLDER.sub("Filled in.", path.read_text())


def test_a_filled_design_passes(tool, root: Path) -> None:
    assert tool.design_problems(filled_design(tool, root)) == []


def test_missing_section_is_reported(tool, root: Path) -> None:
    text = filled_design(tool, root).replace("## Rollout", "## Schedule")
    assert "missing section '## Rollout'" in tool.design_problems(text)


def test_empty_section_is_reported(tool, root: Path) -> None:
    text = filled_design(tool, root).replace("Filled in.\n\n## Goals", "\n## Goals")
    assert "section '## Problem' is empty" in tool.design_problems(text)


def test_one_option_is_not_enough(tool, root: Path) -> None:
    text = filled_design(tool, root)
    text = text.replace("### Option B: Filled in.", "### Approach B").replace(
        "### Option C: Do nothing", "### Fallback"
    )
    assert any("at least 2" in p for p in tool.design_problems(text))


def test_security_subsections_are_required(tool, root: Path) -> None:
    text = filled_design(tool, root).replace("### Trust boundaries", "### Boundaries")
    assert "security section is missing '### Trust boundaries'" in tool.design_problems(text)


def test_empty_security_subsection_is_reported(tool, root: Path) -> None:
    text = filled_design(tool, root)
    start = text.index("### Gaps and unknowns")
    end = text.index("## Rollout")
    text = text[:start] + "### Gaps and unknowns\n\n" + text[end:]
    assert "security subsection '### Gaps and unknowns' is empty" in tool.design_problems(text)


@pytest.mark.parametrize(
    "claim",
    ["The service is compliant.", "This design meets all controls.", "Ready for authorization."],
)
def test_compliance_claims_are_flagged(tool, root: Path, claim: str) -> None:
    text = filled_design(tool, root).replace(
        "### Threats considered\n\n- Filled in.", f"### Threats considered\n\n- {claim}"
    )
    assert any("declares compliance" in p for p in tool.design_problems(text))


def test_the_template_itself_makes_no_compliance_claim(tool, root: Path) -> None:
    assert not any(
        "declares compliance" in p for p in tool.design_problems(filled_design(tool, root))
    )


# ---------------------------------------------------------------- ADRs


def test_adr_locate_defaults(tool, root: Path) -> None:
    info = tool.adr_locate(root)
    assert info["dir"] == "docs/decisions"
    assert info["exists"] is False
    assert info["next_number"] == 1
    assert info["number_width"] == 4


def test_adr_locate_finds_docs_adr_and_reads_records(tool, root: Path) -> None:
    write(root, "docs/adr/0001-use-dynamodb.md", NYGARD)
    write(root, "docs/adr/0002-use-redis.md", MADR_OLD)
    info = tool.adr_locate(root)
    assert info["dir"] == "docs/adr"
    assert info["next_number"] == 3
    assert [(r["number"], r["status"]) for r in info["records"]] == [
        (1, "Accepted"),
        (2, "accepted"),
    ]
    assert info["records"][0]["title"] == "1. Use DynamoDB"


def test_adr_number_width_follows_existing_files(tool, root: Path) -> None:
    write(root, "docs/adr/007-old.md", NYGARD)
    assert tool.adr_locate(root)["next_number"] == 8
    result = tool.adr_new(root, "Next one", "proposed", [], TODAY)
    assert result["path"] == "docs/adr/008-next-one.md"


def test_adr_new_writes_front_matter_and_a_fillable_body(tool, root: Path) -> None:
    result = tool.adr_new(root, "Use Postgres for the audit log", "accepted", [], TODAY)
    assert result["path"] == "docs/decisions/0001-use-postgres-for-the-audit-log.md"
    text = (root / result["path"]).read_text()
    assert text.startswith('---\nstatus: "accepted"\n')
    assert "# Use Postgres for the audit log" in text
    assert tool.read_status(text) == "accepted"


def test_adr_new_rejects_a_status_outside_the_set(tool, root: Path) -> None:
    with pytest.raises(tool.InputError, match="not one of"):
        tool.adr_new(root, "Thing", "maybe", [], TODAY)
    assert not (root / "docs").exists()


def test_supersede_updates_the_old_record_and_links_both_ways(tool, root: Path) -> None:
    old = write(root, "docs/adr/0001-use-dynamodb.md", NYGARD)
    result = tool.adr_new(root, "Use Postgres", "accepted", [1], TODAY)
    new_text = (root / result["path"]).read_text()
    assert "Supersedes [ADR-0001](0001-use-dynamodb.md)." in new_text
    status = tool.read_status(old.read_text())
    assert status == "superseded by [ADR-0002](0002-use-postgres.md)"
    assert "We needed a key-value store." in old.read_text()


def test_supersede_works_on_front_matter_records(tool, root: Path) -> None:
    old = write(root, "docs/decisions/0001-use-redis.md", MADR_OLD)
    tool.adr_new(root, "Use Valkey", "accepted", [1], TODAY)
    assert old.read_text().startswith('---\nstatus: "superseded by [ADR-0002]')


def test_supersede_of_a_missing_record_writes_nothing(tool, root: Path) -> None:
    write(root, "docs/adr/0001-use-dynamodb.md", NYGARD)
    with pytest.raises(tool.InputError, match="no ADR number 9"):
        tool.adr_new(root, "Use Postgres", "accepted", [9], TODAY)
    assert sorted(p.name for p in (root / "docs/adr").iterdir()) == ["0001-use-dynamodb.md"]


def test_supersede_of_a_record_without_a_status_writes_nothing(tool, root: Path) -> None:
    write(root, "docs/adr/0001-no-status.md", "# A record\n\nNo status anywhere.\n")
    with pytest.raises(tool.InputError, match="no status line"):
        tool.adr_new(root, "Replacement", "accepted", [1], TODAY)
    assert [p.name for p in (root / "docs/adr").iterdir()] == ["0001-no-status.md"]


def test_set_status(tool, root: Path) -> None:
    path = write(root, "docs/adr/0001-use-dynamodb.md", NYGARD)
    tool.adr_set_status(root, 1, "deprecated")
    assert tool.read_status(path.read_text()) == "deprecated"


def test_a_prose_line_starting_with_the_word_status_is_not_a_status(tool) -> None:
    assert tool.read_status("# T\n\nStatuses are described below.\n") is None


def test_index_is_reported_when_it_links_the_records(tool, root: Path) -> None:
    write(root, "docs/decisions/0001-use-redis.md", MADR_OLD)
    write(root, "docs/decisions/README.md", "- [0001](0001-use-redis.md) Use Redis\n")
    assert tool.adr_locate(root)["index"] == "README.md"


def filled_adr(tool, root: Path) -> str:
    path = root / tool.adr_new(root, "Use Postgres", "accepted", [], TODAY)["path"]
    text = path.read_text().replace(
        'Chosen option: "[TODO: option]", because [TODO: the deciding reasons].',
        'Chosen option: "Postgres", because the team knows SQL.',
    )
    return tool.PLACEHOLDER.sub("Filled in.", text)


def test_a_filled_adr_passes(tool, root: Path) -> None:
    assert tool.adr_problems(filled_adr(tool, root)) == []


def test_fresh_adr_skeleton_fails_only_on_placeholders_and_chosen_option(tool, root: Path) -> None:
    path = root / tool.adr_new(root, "Skeleton", "proposed", [], TODAY)["path"]
    problems = tool.adr_problems(path.read_text())
    assert any("placeholder" in p for p in problems)


def test_adr_without_chosen_option_line_fails(tool, root: Path) -> None:
    text = filled_adr(tool, root).replace("Chosen option:", "We pick:")
    assert "'## Decision Outcome' needs a line starting 'Chosen option:'" in tool.adr_problems(text)


def test_adr_with_one_option_fails(tool, root: Path) -> None:
    text = filled_adr(tool, root).replace(
        "- Filled in.\n- Filled in.\n\n## Decision Outcome", "- Filled in.\n\n## Decision Outcome"
    )
    assert any("at least 2 options" in p for p in tool.adr_problems(text))


def test_adr_with_a_bad_status_fails(tool, root: Path) -> None:
    text = filled_adr(tool, root).replace('status: "accepted"', 'status: "done"')
    assert any("should start with" in p for p in tool.adr_problems(text))


# ---------------------------------------------------------------- command line


def run_cli(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), "--date", TODAY, *args],
        capture_output=True,
        text=True,
    )


def test_cli_adr_new_prints_json_and_check_reports_placeholders(root: Path) -> None:
    created = run_cli(root, "adr", "new", "Use Postgres")
    assert created.returncode == 0, created.stderr
    path = root / json.loads(created.stdout)["path"]
    checked = run_cli(root, "adr", "check", str(path))
    assert checked.returncode == 1
    assert "unfilled placeholder" in checked.stdout


def test_cli_list_prints_records(root: Path) -> None:
    write(root, "docs/adr/0001-use-dynamodb.md", NYGARD)
    listed = run_cli(root, "adr", "list")
    assert json.loads(listed.stdout)[0]["file"] == "0001-use-dynamodb.md"


def test_cli_errors_exit_two_and_name_the_fix(root: Path) -> None:
    result = run_cli(root, "adr", "new", "Thing", "--supersedes", "4")
    assert result.returncode == 2
    assert result.stderr.startswith("doc_tool.py: no ADR number 4")


def test_cli_check_on_a_missing_file_exits_two(root: Path) -> None:
    result = run_cli(root, "design", "check", str(root / "nope.md"))
    assert result.returncode == 2
    assert "Pass the path" in result.stderr
