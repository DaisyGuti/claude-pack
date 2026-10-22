"""Layout checks for the tickets plugin: links resolve, chat-invocable skills, evals exist."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[2] / "plugins" / "tickets"
SKILLS = sorted(p.parent.name for p in (PLUGIN / "skills").glob("*/SKILL.md"))
EXPECTED_SKILLS = ["daily-grooming", "plan-ticket", "ticket-worker", "work-tickets", "write-ticket"]


def frontmatter(path: Path) -> dict[str, str]:
    """Read the top-level 'key: value' lines of a Markdown file's YAML frontmatter."""
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path}: the opening --- must be line 1"
    block = text.split("---\n", 2)[1]
    return dict(re.findall(r"^([A-Za-z-]+):\s*(.*)$", block, re.M))


def test_the_five_skills_exist() -> None:
    assert SKILLS == EXPECTED_SKILLS


@pytest.mark.parametrize("skill", EXPECTED_SKILLS)
def test_skills_can_be_run_from_chat(skill: str) -> None:
    """The team works from chat, so no skill sets disable-model-invocation."""
    fields = frontmatter(PLUGIN / "skills" / skill / "SKILL.md")
    assert "disable-model-invocation" not in fields


@pytest.mark.parametrize("skill", EXPECTED_SKILLS)
def test_skill_name_matches_folder_and_description_fits(skill: str) -> None:
    fields = frontmatter(PLUGIN / "skills" / skill / "SKILL.md")
    assert fields["name"] == skill
    assert 0 < len(fields["description"]) <= 1024
    assert not re.search(r"claude|anthropic", fields["name"])


@pytest.mark.parametrize("skill", EXPECTED_SKILLS)
def test_skill_body_stays_under_500_lines(skill: str) -> None:
    lines = (PLUGIN / "skills" / skill / "SKILL.md").read_text(encoding="utf-8").splitlines()
    assert len(lines) < 500


def linked_paths(path: Path) -> list[str]:
    """Plugin-relative targets of every ${CLAUDE_PLUGIN_ROOT}/ or ${CLAUDE_SKILL_DIR}/ link."""
    text = path.read_text(encoding="utf-8")
    found = re.findall(r"\$\{CLAUDE_PLUGIN_ROOT\}/([\w./-]+?)(?=[)`\s]|$)", text)
    skill_dir = path.parent.relative_to(PLUGIN).as_posix()
    found += [
        f"{skill_dir}/{rel}"
        for rel in re.findall(r"\$\{CLAUDE_SKILL_DIR\}/([\w./-]+?)(?=[)`\s]|$)", text)
    ]
    return found


@pytest.mark.parametrize("skill", EXPECTED_SKILLS)
def test_every_path_a_skill_links_exists(skill: str) -> None:
    targets = linked_paths(PLUGIN / "skills" / skill / "SKILL.md")
    assert targets, "a skill with no links to its references is suspicious"
    for rel in targets:
        if rel.endswith("/") or "*" in rel:
            continue  # a folder or a glob used in an allowed-tools rule
        assert (PLUGIN / rel).exists(), f"{skill}: {rel} does not exist"


def test_script_paths_in_allowed_tools_exist() -> None:
    for skill in EXPECTED_SKILLS:
        rules = frontmatter(PLUGIN / "skills" / skill / "SKILL.md").get("allowed-tools", "")
        for rel in re.findall(r"\$\{CLAUDE_PLUGIN_ROOT\}/(scripts/[\w.-]+)", rules):
            script = PLUGIN / rel
            assert script.is_file(), f"{skill}: allowed-tools names missing {rel}"
            assert script.stat().st_mode & 0o111, f"{rel} is not executable"


def test_reference_files_named_in_prose_exist() -> None:
    names = {p.name for p in (PLUGIN / "references").rglob("*.md")}
    names |= {p.name for p in PLUGIN.glob("skills/*/references/*.md")}
    for doc in [
        *PLUGIN.glob("references/*.md"),
        *PLUGIN.glob("skills/*/references/*.md"),
        *PLUGIN.glob("agents/*.md"),
    ]:
        for ref in re.findall(r"`([a-z][a-z-]+\.md)`", doc.read_text(encoding="utf-8")):
            if ref in {
                "registry.md",
                "registry.example.md",
                "SKILL.md",
                "CLAUDE.md",
                "AGENTS.md",
                "CONTRIBUTING.md",
                "README.md",
            }:
                continue
            assert ref in names, f"{doc.relative_to(PLUGIN)} names {ref}, which does not exist"


def test_worker_agent_is_isolated_and_least_privilege() -> None:
    fields = frontmatter(PLUGIN / "agents" / "ticket-worker.md")
    assert fields["name"] == "ticket-worker"
    assert fields["isolation"] == "worktree"
    assert "Skill" not in fields["tools"]
    assert fields["model"] in {"haiku", "sonnet", "opus", "inherit"}
    assert int(fields["maxTurns"]) > 0


def test_worker_reviews_its_diff_before_committing() -> None:
    """The worker holds the Agent tool, runs core:reviewer before any commit on both landing
    paths (section 7 and the held review in section 9), and reports the review in each body."""
    path = PLUGIN / "agents" / "ticket-worker.md"
    tools = [t.strip() for t in frontmatter(path)["tools"].split(",")]
    assert "Agent" in tools
    body = path.read_text(encoding="utf-8")
    land = body[body.index("## 7. Land the work") : body.index("## 8. After the review opens")]
    held = body[body.index("## 9. Needs manual action") : body.index("## 10. Final report")]
    assert land.index("**Pre-commit review.**") < land.index("**Commit.**")
    assert "`core:reviewer`" in land
    assert "blocked_review_findings" in land
    assert "before committing or pushing any of them" in land
    assert "**Pre-commit review**" in held
    assert "the review summary" in land
    assert "the review summary" in held
    manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert "core" in manifest.get("dependencies", [])


def test_work_tickets_runs_a_rolling_pool_and_says_so_everywhere() -> None:
    """The skill and its procedure agree on the pool size, and no file still says waves."""
    skill = (PLUGIN / "skills" / "work-tickets" / "SKILL.md").read_text(encoding="utf-8")
    procedure = (PLUGIN / "skills" / "work-tickets" / "references" / "orchestrator.md").read_text(
        encoding="utf-8"
    )
    default = re.compile(r"max-parallel`? \(5 by default\)|\*\*max-parallel:\*\* 5")
    assert default.search(skill), "SKILL.md must state the default pool size of 5"
    assert default.search(procedure), "orchestrator.md must state the default pool size of 5"
    assert "run_in_background: true" in procedure
    stale = [
        str(path.relative_to(PLUGIN))
        for path in (
            PLUGIN / "README.md",
            PLUGIN / "skills" / "work-tickets" / "SKILL.md",
            PLUGIN / "skills" / "work-tickets" / "references" / "orchestrator.md",
        )
        if re.search(r"\bwaves?\b", path.read_text(encoding="utf-8"), re.I)
    ]
    assert not stale, f"still describes waves: {stale}"


def test_scripts_are_executable_with_a_shebang() -> None:
    for script in (PLUGIN / "scripts").glob("*.py"):
        assert script.stat().st_mode & 0o111, f"{script.name} is not executable"
        assert script.read_text(encoding="utf-8").startswith("#!/usr/bin/env python3")


@pytest.mark.parametrize("skill", EXPECTED_SKILLS)
def test_each_skill_has_trigger_and_no_trigger_evals(skill: str) -> None:
    cases = sorted((PLUGIN / "evals").glob(f"{skill}-*/prompt.md"))
    assert len(cases) >= 3
    for prompt in cases:
        assert list((prompt.parent / "graders").glob("*.md")), f"{prompt.parent.name} has no grader"
    near_miss = (PLUGIN / "evals" / f"{skill}-near-miss" / "graders").glob("*.md")
    texts = [g.read_text(encoding="utf-8") for g in near_miss]
    assert any("min: 0" in t and "max: 0" in t and "arm: both" in t for t in texts)


def test_the_agent_has_a_delegation_eval() -> None:
    graders = (PLUGIN / "evals" / "ticket-worker-agent-delegates-when-asked" / "graders").glob(
        "*.md"
    )
    assert any("tool: Agent" in g.read_text(encoding="utf-8") for g in graders)


def test_no_personal_paths_or_tool_names_leak_into_the_plugin() -> None:
    banned = re.compile(
        r"(?-i:/Users/)|\bcodex\b|\$work-tickets|\$ticket-worker|\$write-ticket", re.I
    )
    for path in PLUGIN.rglob("*"):
        if (
            path.is_file()
            and path.suffix in {".md", ".py", ".json"}
            and "evals/results" not in str(path)
        ):
            hit = banned.search(path.read_text(encoding="utf-8"))
            assert hit is None, f"{path.relative_to(PLUGIN)} mentions {hit.group(0)!r}"
