"""Structure checks for the team-comms plugin: conventions, evals, and the draft-only rule."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[2] / "plugins" / "team-comms"
SKILLS = sorted(p.parent.name for p in (PLUGIN / "skills").glob("*/SKILL.md"))
# Frontmatter fields Claude Code documents for skills (authoring guide G9 to G19).
ALLOWED_FIELDS = {
    "name",
    "description",
    "when_to_use",
    "argument-hint",
    "arguments",
    "disable-model-invocation",
    "user-invocable",
    "allowed-tools",
    "disallowed-tools",
    "model",
    "effort",
    "context",
    "agent",
    "background",
    "hooks",
    "paths",
    "shell",
}
DESCRIPTION_LIMIT = 1536  # description plus when_to_use, authoring guide G4
SKILL_LINE_LIMIT = 500  # authoring guide G25
TOC_THRESHOLD = 100  # reference files longer than this need a table of contents (G28)
WRITE_TOOLS = ("slack_send_message", "slack_schedule_message", "slack_add_reaction")
MIN_EVALS_PER_SKILL = 3
# Skills the model cannot invoke have no should-trigger eval.
USER_ONLY = {"slack-send"}


def frontmatter(path: Path) -> dict[str, str]:
    """Read the frontmatter keys; supports plain, quoted and folded (>-) scalar values."""
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines and lines[0] == "---", f"{path}: opening --- must be line 1"
    fields: dict[str, str] = {}
    key: str | None = None
    for line in lines[1:]:
        if line == "---":
            return fields
        if key and line.startswith("  "):  # continuation of a folded block scalar
            fields[key] = f"{fields[key]} {line.strip()}".strip()
            continue
        match = re.match(r"^([A-Za-z][\w-]*):\s*(.*)$", line)
        assert match, f"{path}: cannot read frontmatter line {line!r}"
        key, value = match.group(1), match.group(2).strip()
        if value in {">-", ">", "|", "|-"}:
            fields[key] = ""
            continue
        key = None
        # YAML ends a plain (unquoted) value at " #", which silently truncates a description.
        assert value.startswith(('"', "'")) or " #" not in value, (
            f"{path}: ' #' in the unquoted value of {match.group(1)}; quote it or use a >- block"
        )
        fields[match.group(1)] = value
    raise AssertionError(f"{path}: frontmatter never closes")


def markdown_files(*, include_assets: bool = False) -> list[Path]:
    files = [
        p
        for p in PLUGIN.rglob("*.md")
        if "evals" not in p.relative_to(PLUGIN).parts
        and (include_assets or "assets" not in p.relative_to(PLUGIN).parts)
    ]
    return sorted(files)


def test_the_expected_skills_exist() -> None:
    assert SKILLS == [
        "adr",
        "design-doc",
        "slack-catchup",
        "slack-draft",
        "slack-send",
        "status-update",
    ]


@pytest.mark.parametrize("skill", SKILLS)
def test_frontmatter_is_valid(skill: str) -> None:
    fields = frontmatter(PLUGIN / "skills" / skill / "SKILL.md")
    assert fields["name"] == skill
    assert re.fullmatch(r"[a-z0-9-]{1,64}", skill)
    assert "claude" not in skill and "anthropic" not in skill
    assert set(fields) <= ALLOWED_FIELDS, f"unknown fields: {set(fields) - ALLOWED_FIELDS}"
    text = fields["description"] + fields.get("when_to_use", "")
    assert 0 < len(text) <= DESCRIPTION_LIMIT
    assert not re.match(r"^(I|You|We)\b", fields["description"]), (
        "write the description in third person"
    )


@pytest.mark.parametrize("skill", SKILLS)
def test_skill_body_is_short_and_references_exist(skill: str) -> None:
    folder = PLUGIN / "skills" / skill
    text = (folder / "SKILL.md").read_text(encoding="utf-8")
    assert len(text.splitlines()) < SKILL_LINE_LIMIT
    for variable, base in (("CLAUDE_SKILL_DIR", folder), ("CLAUDE_PLUGIN_ROOT", PLUGIN)):
        for rel in re.findall(r"\$\{" + variable + r"\}/([\w./-]+)", text):
            assert (base / rel.rstrip(".")).exists(), f"{skill}: {variable}/{rel} does not exist"


@pytest.mark.parametrize(
    "path", sorted((PLUGIN / "skills").glob("*/references/*.md")) + sorted(PLUGIN.glob("docs/*.md"))
)
def test_long_reference_files_have_a_contents_list(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if len(text.splitlines()) > TOC_THRESHOLD:
        assert "## Contents" in text, (
            f"{path.name} is over {TOC_THRESHOLD} lines and needs a Contents list"
        )


def test_references_sit_one_level_deep() -> None:
    for skill in SKILLS:
        for path in (PLUGIN / "skills" / skill).rglob("*"):
            if path.is_file() and path.name != "SKILL.md":
                depth = len(path.relative_to(PLUGIN / "skills" / skill).parts)
                assert depth <= 2, f"{path} is nested too deep"


def test_posting_lives_only_in_slack_send() -> None:
    send = frontmatter(PLUGIN / "skills" / "slack-send" / "SKILL.md")
    assert send["disable-model-invocation"] == "true"
    for skill in SKILLS:
        if skill == "slack-send":
            continue
        for path in (PLUGIN / "skills" / skill).rglob("*.md"):
            text = path.read_text(encoding="utf-8")
            for tool in WRITE_TOOLS:
                hits = [
                    m
                    for m in re.finditer(tool, text)
                    if f"slack:{tool}" in text[m.start() - 6 : m.end()]
                ]
                assert not hits, f"{path} calls {tool}; only slack-send may write to Slack"


def test_draft_only_rule_is_stated_at_the_top_of_slack_draft() -> None:
    text = (PLUGIN / "skills" / "slack-draft" / "SKILL.md").read_text(encoding="utf-8")
    body = text.split("---", 2)[2]
    assert "drafts only" in body.split("## 1.")[0].lower()


def test_every_slack_tool_named_in_a_skill_is_listed_in_the_connection_guide() -> None:
    guide = (PLUGIN / "docs" / "connect-slack.md").read_text(encoding="utf-8")
    for path in PLUGIN.glob("skills/*/SKILL.md"):
        for tool in re.findall(r"slack:(slack_\w+)", path.read_text(encoding="utf-8")):
            assert f"`{tool}`" in guide, (
                f"{path.parent.name} uses {tool}, missing from connect-slack.md"
            )


def eval_cases(skill: str) -> list[Path]:
    return sorted(p for p in (PLUGIN / "evals").glob(f"{skill}-*") if p.is_dir())


@pytest.mark.parametrize("skill", SKILLS)
def test_each_skill_has_enough_eval_cases(skill: str) -> None:
    cases = eval_cases(skill)
    assert len(cases) >= MIN_EVALS_PER_SKILL, f"{skill} has {len(cases)} eval cases"
    for case in cases:
        assert (case / "prompt.md").is_file(), f"{case.name} has no prompt.md"
        assert list((case / "graders").glob("*.md")), f"{case.name} has no grader"
        prompt = (case / "prompt.md").read_text(encoding="utf-8").split("---", 2)[2].lower()
        assert "skill" not in prompt, (
            f"{case.name} should read like a user request, not name a skill"
        )
        if skill != "slack-send":
            assert "team-comms:" not in prompt, f"{case.name} names a plugin command"


@pytest.mark.parametrize("skill", SKILLS)
def test_each_skill_has_a_trigger_case_and_a_near_miss(skill: str) -> None:
    graders = [g for case in eval_cases(skill) for g in case.glob("graders/*.md")]
    texts = [g.read_text(encoding="utf-8") for g in graders]
    names_skill = [t for t in texts if "tool: Skill" in t and f'{skill}"' in t]
    near_miss = [t for t in names_skill if "min: 0" in t and "max: 0" in t and "arm: both" in t]
    assert near_miss, f"{skill} needs a near-miss case (min 0, max 0, arm both)"
    if skill not in USER_ONLY:
        trigger = [t for t in names_skill if "min: 0" not in t]
        assert trigger, f"{skill} needs a should-trigger case with a Skill tool_used grader"


def test_prose_follows_the_writing_rules(load_script) -> None:
    lint = load_script("lint_draft")
    problems = []
    for path in markdown_files():
        for finding in lint.check_prose(path.read_text(encoding="utf-8")):
            if finding.rule in {"contrast", "hype"}:
                problems.append(f"{path.relative_to(PLUGIN)}:{finding.line}: {finding.excerpt}")
    assert not problems, "\n".join(problems)


def test_no_personal_paths_or_secrets_ship_in_the_plugin(load_script) -> None:
    lint = load_script("lint_draft")
    for path in PLUGIN.rglob("*"):
        if not path.is_file() or path.suffix not in {".md", ".py", ".sh", ".json", ".yaml"}:
            continue
        text = path.read_text(encoding="utf-8")
        assert "/Users/" not in text, f"{path} holds a machine path"
        assert not re.search(r"~/[A-Za-z]", text), f"{path} holds a home-relative path"
        if "evals" in path.parts:
            continue  # eval prompts carry the documented example key on purpose
        assert not lint.check_secrets(text), f"{path} looks like it holds a secret"


def test_scripts_are_executable_python_with_a_shebang() -> None:
    for path in (PLUGIN / "scripts").glob("*.py"):
        assert path.stat().st_mode & 0o111, f"{path.name} is not executable"
        assert path.read_text(encoding="utf-8").startswith("#!/usr/bin/env python3")


def test_regex_graders_use_the_flags_key_not_inline_flags() -> None:
    """The eval runner rejects a pattern such as (?i)...; flags go in a `flags:` key."""
    for grader in (PLUGIN / "evals").glob("*/graders/*.md"):
        text = grader.read_text(encoding="utf-8")
        if "type: regex" in text:
            pattern = re.search(r"^pattern: '(.*)'$", text, re.M)
            assert pattern, f"{grader} has no pattern"
            assert not re.match(r"\(\?[a-z]+\)", pattern.group(1)), f"{grader} uses an inline flag"
