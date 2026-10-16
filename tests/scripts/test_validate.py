"""Tests for scripts/validate.py: which validator output counts as a failure."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "validate", Path(__file__).resolve().parents[2] / "scripts" / "validate.py"
)
assert SPEC and SPEC.loader
validate = importlib.util.module_from_spec(SPEC)
sys.modules["validate"] = validate
SPEC.loader.exec_module(validate)

VERSION_WARNING = {"path": "version", "message": "No version specified. Consider adding one"}


def test_missing_version_warning_is_allowed() -> None:
    report = {"success": True, "manifest": {"errors": [], "warnings": [VERSION_WARNING]}}
    assert validate.blocking_problems(report) == []


def test_other_warning_blocks() -> None:
    other = {"path": "skills", "message": "Default skills/ folder is ignored"}
    report = {"success": True, "manifest": {"errors": [], "warnings": [VERSION_WARNING, other]}}
    assert validate.blocking_problems(report) == [
        "warning: skills: Default skills/ folder is ignored"
    ]


def test_error_blocks_even_inside_contents() -> None:
    report = {
        "success": False,
        "manifest": {"errors": [], "warnings": []},
        "contents": [{"errors": [{"path": "SKILL.md", "message": "bad frontmatter"}]}],
    }
    assert validate.blocking_problems(report) == ["error: SKILL.md: bad frontmatter"]


def test_failure_without_listed_error_still_blocks() -> None:
    assert validate.blocking_problems({"success": False}) == [
        "validator reported failure without a listed error"
    ]


# --- Frontmatter checks -------------------------------------------------------------------


def write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def skill_problems(tmp_path: Path, frontmatter: str) -> list[str]:
    path = write(tmp_path, "s/SKILL.md", f"---\n{frontmatter}\n---\nBody\n")
    return validate.check_named_component(path, "skill")


def test_clean_skill_passes(tmp_path: Path) -> None:
    assert (
        skill_problems(tmp_path, "name: good-skill\ndescription: Does a thing. Use when asked.")
        == []
    )


def test_opening_marker_must_be_line_one(tmp_path: Path) -> None:
    path = write(tmp_path, "s/SKILL.md", "\n---\nname: a\ndescription: b\n---\n")
    (problem,) = validate.check_named_component(path, "skill")
    assert "opening `---` must be line 1" in problem


def test_missing_closing_marker(tmp_path: Path) -> None:
    path = write(tmp_path, "s/SKILL.md", "---\nname: a\ndescription: b\nBody\n")
    (problem,) = validate.check_named_component(path, "skill")
    assert "no closing `---`" in problem


def test_missing_description_and_name(tmp_path: Path) -> None:
    problems = skill_problems(tmp_path, "argument-hint: x")
    assert any("non-empty `name`" in p for p in problems)
    assert any("non-empty `description`" in p for p in problems)


def test_plain_description_cut_at_space_hash(tmp_path: Path) -> None:
    problems = skill_problems(tmp_path, 'name: a\ndescription: Use for "take #42 to a PR"')
    assert len(problems) == 1 and "` #`" in problems[0]


def test_plain_description_with_colon_space(tmp_path: Path) -> None:
    problems = skill_problems(tmp_path, "name: a\ndescription: Does it. Out of scope: other things")
    assert len(problems) == 1 and "colon" in problems[0]


def test_folded_and_quoted_descriptions_may_hold_colons_and_hashes(tmp_path: Path) -> None:
    folded = "name: a\ndescription: >-\n  Use for #42 and scope: this."
    quoted = 'name: a\ndescription: "Use for #42 and scope: this."'
    assert skill_problems(tmp_path, folded) == []
    assert skill_problems(tmp_path, quoted) == []


def test_multiline_plain_description_is_read_whole(tmp_path: Path) -> None:
    ok = "name: a\ndescription:\n  First line\n  second line"
    bad = "name: a\ndescription:\n  First line\n  second # comment"
    assert skill_problems(tmp_path, ok) == []
    assert len(skill_problems(tmp_path, bad)) == 1


def test_unclosed_quote_and_bracket(tmp_path: Path) -> None:
    assert any("never closes" in p for p in skill_problems(tmp_path, 'name: a\ndescription: "open'))
    assert any("never closes" in p for p in skill_problems(tmp_path, "name: a\ndescription: [open"))


def test_listing_length_limit(tmp_path: Path) -> None:
    long_text = "x" * 1500
    problems = skill_problems(
        tmp_path, f"name: a\ndescription: {long_text}\nwhen_to_use: {'y' * 100}"
    )
    assert len(problems) == 1 and "1536" in problems[0]


def test_skill_name_rules(tmp_path: Path) -> None:
    assert any("lowercase" in p for p in skill_problems(tmp_path, "name: Bad_Name\ndescription: d"))
    assert any(
        "claude" in p for p in skill_problems(tmp_path, "name: my-claude-helper\ndescription: d")
    )


def test_lists_and_maps_are_not_read_as_scalars(tmp_path: Path) -> None:
    text = "name: a\ndescription: d\nskills:\n  - ui-design:ux-review\nmetadata:\n  note: x: y"
    assert skill_problems(tmp_path, text) == []


def test_agent_file_needs_description(tmp_path: Path) -> None:
    path = write(tmp_path, "agents/ag.md", "---\nname: ag\ntools: Read\n---\nBody\n")
    (problem,) = validate.check_named_component(path, "agent")
    assert "non-empty `description`" in problem


def test_agent_name_may_not_hold_colon(tmp_path: Path) -> None:
    path = write(tmp_path, "agents/ag.md", "---\nname: 'a:b'\ndescription: d\n---\nBody\n")
    (problem,) = validate.check_named_component(path, "agent")
    assert "may not hold `:`" in problem


def test_regex_grader_rejects_inline_flags(tmp_path: Path) -> None:
    bad = write(tmp_path, "g/bad.md", "---\ntype: regex\npattern: '(?i)hello'\n---\n")
    good = write(tmp_path, "g/good.md", "---\ntype: regex\npattern: 'hello'\nflags: i\n---\n")
    other = write(tmp_path, "g/llm.md", "---\ntype: llm\n---\nPASS if (?i) appears.\n")
    assert len(validate.check_eval_grader(bad)) == 1
    assert validate.check_eval_grader(good) == []
    assert validate.check_eval_grader(other) == []


def test_eval_prompt_description_with_colon_must_be_quoted(tmp_path: Path) -> None:
    bad = write(tmp_path, "p/bad.md", "---\ndescription: Near miss: not this\n---\nPrompt\n")
    good = write(tmp_path, "p/good.md", '---\ndescription: "Near miss: not this"\n---\nPrompt\n')
    assert len(validate.check_eval_prompt(bad)) == 1
    assert validate.check_eval_prompt(good) == []


def test_check_plugin_files_walks_skills_agents_and_evals(tmp_path: Path) -> None:
    write(tmp_path, "skills/a/SKILL.md", "---\nname: a\ndescription: fine\n---\n")
    write(tmp_path, "agents/ag.md", "---\nname: ag\n---\n")
    write(tmp_path, "evals/c/prompt.md", "---\ndescription: x: y\n---\nPrompt\n")
    write(tmp_path, "evals/c/graders/g.md", "---\ntype: regex\npattern: '(?s)a'\n---\n")
    problems = validate.check_plugin_files(tmp_path)
    assert len(problems) == 3


def test_validator_targets_include_existing_component_folders(tmp_path: Path) -> None:
    (tmp_path / "skills").mkdir()
    targets = validate.validator_targets(tmp_path)
    assert targets == [tmp_path, tmp_path / "skills"]


def test_every_plugin_in_the_repo_passes_the_file_checks() -> None:
    plugins = sorted((validate.ROOT / "plugins").iterdir())
    problems = [p for plugin in plugins for p in validate.check_plugin_files(plugin)]
    assert problems == []
