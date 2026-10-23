"""Structural rules for the core plugin's agents, skills and references (no network, no model)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[2] / "plugins" / "core"
AGENTS = sorted((PLUGIN / "agents").glob("*.md"))
SKILLS = sorted((PLUGIN / "skills").glob("*/SKILL.md"))
DESCRIPTION_LIMIT = 1536  # description plus when_to_use, per Claude Code's skill listing cap
SKILL_LINE_LIMIT = 500
REFERENCE_TOC_THRESHOLD = 100


def frontmatter(path: Path) -> dict[str, str]:
    """Top-level `key: value` pairs of the YAML frontmatter; the opening --- must be line 1."""
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "---", f"{path}: opening --- must be line 1"
    end = lines.index("---", 1)
    pairs = {}
    for line in lines[1:end]:
        match = re.match(r"^([A-Za-z][A-Za-z0-9-]*):\s*(.*)$", line)
        if match:
            pairs[match.group(1)] = match.group(2).strip()
    return pairs


def tools(path: Path) -> set[str]:
    return {t.strip() for t in frontmatter(path)["tools"].split(",")}


def test_the_plugin_ships_the_expected_agents_and_skills():
    assert [p.stem for p in AGENTS] == ["eng", "forward-tester", "reviewer"]
    assert [p.parent.name for p in SKILLS] == ["eng", "project-setup"]


@pytest.mark.parametrize("path", AGENTS, ids=lambda p: p.stem)
def test_agent_frontmatter(path):
    fm = frontmatter(path)
    assert fm["name"] == path.stem
    assert fm["description"]
    assert "Skill" not in tools(path), "list skills under `skills:`, never in `tools`"
    assert fm["model"] in {"haiku", "sonnet", "opus", "inherit"}
    assert fm["effort"] in {"low", "medium", "high", "xhigh", "max"}
    assert int(fm["maxTurns"]) > 0
    for ignored in ("hooks", "mcpServers", "permissionMode", "initialPrompt"):
        assert ignored not in fm, f"plugin agents silently ignore {ignored}"


@pytest.mark.parametrize("name", ["reviewer", "forward-tester"])
def test_checking_agents_cannot_edit_or_spawn(name):
    granted = tools(PLUGIN / "agents" / f"{name}.md")
    assert granted.isdisjoint({"Edit", "Write", "NotebookEdit", "Agent", "WebFetch", "WebSearch"})


def test_only_eng_spawns_subagents():
    assert "Agent" in tools(PLUGIN / "agents" / "eng.md")


def test_eng_guards_its_own_turn_budget():
    # A run that hit the cap mid-stack-test ended with no report; these rules prevent that.
    body = (PLUGIN / "agents" / "eng.md").read_text(encoding="utf-8")
    assert "write\nthe report" in body or "write the report" in body
    assert "Multi-step runs go to `core:forward-tester`" in body
    assert int(frontmatter(PLUGIN / "agents" / "forward-tester.md")["maxTurns"]) >= 60


def test_gates_run_at_the_repos_full_parallelism():
    # An eng run capped a 16-worker suite at 4; the rule is generic, never repo-specific.
    standards = (PLUGIN / "skills" / "eng" / "references" / "engineering-standards.md").read_text(
        encoding="utf-8"
    )
    assert "- Run tests and gates at the repo's full parallelism" in standards
    assert "**Run tests and gates at the repo's full parallelism.**" in standards
    assert "Never lower the worker count without a stated reason" in standards
    eng = (PLUGIN / "agents" / "eng.md").read_text(encoding="utf-8")
    assert "at the repo's full parallelism" in eng
    worker = (PLUGIN.parent / "tickets" / "agents" / "ticket-worker.md").read_text(encoding="utf-8")
    assert "**Run at the repo's full parallelism.**" in worker


def test_new_environment_variables_land_in_the_example_file():
    # A change added 29 variables a developer could not discover; the rule is generic.
    standards = (PLUGIN / "skills" / "eng" / "references" / "engineering-standards.md").read_text(
        encoding="utf-8"
    )
    title = "Every new environment variable lands in the repo's example env file"
    assert f"- {title}" in standards
    assert f"**{title}.**" in standards
    worker = (PLUGIN.parent / "tickets" / "agents" / "ticket-worker.md").read_text(encoding="utf-8")
    assert "committed example env file" in worker


@pytest.mark.parametrize("path", SKILLS, ids=lambda p: p.parent.name)
def test_skill_frontmatter_and_size(path):
    fm = frontmatter(path)
    assert fm["name"] == path.parent.name
    assert re.fullmatch(r"[a-z0-9-]{1,64}", fm["name"])
    assert "claude" not in fm["name"] and "anthropic" not in fm["name"]
    assert 0 < len(fm["description"]) + len(fm.get("when_to_use", "")) <= DESCRIPTION_LIMIT
    assert len(path.read_text(encoding="utf-8").splitlines()) < SKILL_LINE_LIMIT


def test_the_eng_skill_forks_into_the_eng_agent():
    fm = frontmatter(PLUGIN / "skills" / "eng" / "SKILL.md")
    assert fm["context"] == "fork"
    assert fm["agent"] == "core:eng"
    assert (PLUGIN / "agents" / "eng.md").is_file()


@pytest.mark.parametrize("path", [*AGENTS, *SKILLS], ids=lambda p: f"{p.parent.name}/{p.name}")
def test_variable_paths_and_links_resolve(path):
    text = path.read_text(encoding="utf-8")
    skill_dir = path.parent
    for ref in re.findall(r"\$\{CLAUDE_PLUGIN_ROOT\}/([\w./-]+\.(?:md|py))", text):
        assert (PLUGIN / ref).is_file(), f"{path.name}: ${{CLAUDE_PLUGIN_ROOT}}/{ref} is missing"
    for ref in re.findall(r"\$\{CLAUDE_SKILL_DIR\}/([\w./-]+\.(?:md|py))", text):
        assert (skill_dir / ref).is_file(), f"{path.name}: ${{CLAUDE_SKILL_DIR}}/{ref} is missing"
    for ref in re.findall(r"\]\(((?:references|assets|scripts)/[^)#]+)", text):
        assert (skill_dir / ref).is_file(), f"{path.name}: link {ref} is missing"


def test_long_reference_files_have_a_table_of_contents():
    for path in (PLUGIN / "skills").glob("*/references/*.md"):
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) > REFERENCE_TOC_THRESHOLD:
            assert "## Contents" in lines, f"{path.name} passes 100 lines and needs a contents list"


def test_no_personal_or_machine_specific_text_ships():
    # `~/.claude/` is the standard per-user Claude Code folder, so it is allowed.
    banned = re.compile(r"/Users/|/home/\w|~/(?!\.claude)|daisy|codex|openai|chatgpt", re.I)
    shipped = [
        p
        for p in PLUGIN.rglob("*")
        if p.is_file()
        and p.suffix in {".md", ".py", ".json"}
        and ".claude-plugin" not in p.parts
        and "evals" not in p.parts
        # This checker carries the machine-path patterns it searches other files for.
        and p.name != "check_claude_md.py"
    ]
    for path in shipped:
        hit = banned.search(path.read_text(encoding="utf-8"))
        assert hit is None, f"{path.relative_to(PLUGIN)} contains {hit and hit.group()!r}"


def eval_cases(prefix: str) -> list[Path]:
    return sorted(p for p in (PLUGIN / "evals").glob(f"{prefix}-*") if (p / "prompt.md").is_file())


def grader_texts(case: Path) -> list[str]:
    graders = sorted((case / "graders").glob("*.md"))
    assert graders, f"{case.name} has no grader"
    return [g.read_text(encoding="utf-8") for g in graders]


@pytest.mark.parametrize("skill", ["eng", "project-setup"])
def test_each_skill_has_trigger_and_near_miss_evals(skill):
    cases = eval_cases(f"{skill}-skill")
    assert len(cases) >= 3
    texts = [t for c in cases for t in grader_texts(c)]
    assert any("tool: Skill" in t and "min: 0" not in t and skill in t for t in texts)
    near_miss = [t for t in texts if "tool: Skill" in t and "max: 0" in t and "arm: both" in t]
    assert near_miss


@pytest.mark.parametrize("agent", ["eng", "reviewer", "forward-tester"])
def test_each_agent_has_a_delegation_eval(agent):
    texts = [t for c in eval_cases(f"{agent}-agent") for t in grader_texts(c)]
    assert any("tool: Agent" in t and f"core:{agent}" in t and "min: 0" not in t for t in texts)
