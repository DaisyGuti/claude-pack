"""Structure checks for plugins/security that `claude plugin validate` does not make.

They hold the house conventions in docs/conventions.md that a script can verify: size and
description limits, evals per skill and agent, no machine paths, and templates that pass the
document checkers they are written for.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins/security"
FIXTURES = Path(__file__).parent / "fixtures"
SKILLS = sorted(p for p in (PLUGIN / "skills").iterdir() if p.is_dir())
EVALS = PLUGIN / "evals"


def _frontmatter(path: Path) -> tuple[dict[str, str], str]:
    text = path.read_text()
    assert text.startswith("---\n"), f"{path}: the opening --- must be line 1"
    head, _, body = text[4:].partition("\n---\n")
    fields = {}
    for line in head.splitlines():
        match = re.match(r"^([A-Za-z-]+):\s*(.*)$", line)
        if match:
            fields[match.group(1)] = match.group(2).strip().strip('"')
    return fields, body


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, PLUGIN / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_the_plugin_has_the_expected_skills_and_agent():
    assert [p.name for p in SKILLS] == ["compliance-map", "security-scan", "threat-model"]
    assert (PLUGIN / "agents/security-auditor.md").is_file()


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.name)
def test_skill_frontmatter_and_size(skill):
    fields, body = _frontmatter(skill / "SKILL.md")
    assert fields["name"] == skill.name
    assert re.fullmatch(r"[a-z0-9-]{1,64}", fields["name"])
    assert "claude" not in fields["name"] and "anthropic" not in fields["name"]
    description = fields["description"]
    assert not re.match(r"(I|You|We)\b", description), "write the description in third person"
    # Claude Code truncates description plus when_to_use at 1,536 characters.
    assert len(description) + len(fields.get("when_to_use", "")) <= 1536
    assert len((skill / "SKILL.md").read_text().splitlines()) < 500
    assert "disable-model-invocation" not in fields, "none of these skills has a side effect"


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.name)
def test_every_reference_linked_from_a_skill_exists_one_level_deep(skill):
    text = (skill / "SKILL.md").read_text()
    links = re.findall(r"\]\((references/[^)]+)\)", text)
    assert links, "a skill with depth should link its references"
    for link in links:
        assert (skill / link).is_file(), f"{skill.name}: {link} is missing"
        assert link.count("/") == 1, "references sit one level deep"
    for ref in (skill / "references").glob("*.md"):
        lines = ref.read_text().splitlines()
        if len(lines) > 100:
            assert any(line.lower().startswith("contents") for line in lines[:8]), (
                f"{ref.name} is over 100 lines and needs a table of contents"
            )


def test_the_agent_is_least_privilege_and_self_contained():
    fields, body = _frontmatter(PLUGIN / "agents/security-auditor.md")
    assert fields["name"] == "security-auditor"
    tools = {t.strip() for t in fields["tools"].split(",")}
    assert tools <= {"Read", "Grep", "Glob", "Bash"}, "no Edit, Write or Skill"
    assert fields["model"] == "sonnet"
    assert int(fields["maxTurns"]) > 0
    for ignored in ("permissionMode", "hooks", "mcpServers", "initialPrompt"):
        assert ignored not in fields, f"plugin agents ignore {ignored}"
    for section in ("## Inputs", "## Procedure", "## What to return"):
        assert section in body


def _cases_for(prefix: str) -> list[Path]:
    return sorted(p for p in EVALS.iterdir() if p.is_dir() and p.name.startswith(prefix + "-"))


def _graders(case: Path) -> list[str]:
    return [g.read_text() for g in sorted((case / "graders").glob("*.md"))]


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.name)
def test_each_skill_has_three_evals_with_a_trigger_case_and_a_near_miss(skill):
    cases = _cases_for(skill.name)
    assert len(cases) >= 3
    all_graders = [text for case in cases for text in _graders(case)]
    assert any(
        "tool: Skill" in text and skill.name in text and "min: 0" not in text
        for text in all_graders
    ), "needs a should-trigger grader"
    assert any(
        "min: 0" in text and "max: 0" in text and "arm: both" in text and skill.name in text
        for text in all_graders
    ), "needs a near-miss case that must not trigger the skill"


def test_the_agent_has_a_delegation_case_and_a_near_miss():
    cases = _cases_for("security-auditor")
    graders = [text for case in cases for text in _graders(case)]
    assert any(
        "tool: Agent" in g and "security-auditor" in g and "min: 0" not in g for g in graders
    )
    assert any("tool: Agent" in g and "min: 0" in g and "max: 0" in g for g in graders)


def test_every_eval_case_has_a_prompt_and_at_least_one_grader():
    for case in sorted(p for p in EVALS.iterdir() if p.is_dir() and p.name != "results"):
        assert (case / "prompt.md").is_file(), case.name
        assert _graders(case), f"{case.name} has no grader"
        fields, body = _frontmatter(case / "prompt.md")
        assert body.strip(), f"{case.name} has an empty prompt"
        assert "threat-model" not in body and "security-scan" not in body, (
            f"{case.name}: the prompt must not name the skill"
        )
        assert "compliance-map" not in body and "security-auditor" not in body


def test_no_machine_paths_or_personal_names_in_the_plugin_or_its_tests():
    pattern = re.compile(r"/Users/|/home/\w+|/private/tmp|~/|daisy", re.IGNORECASE)
    for root in (PLUGIN, ROOT / "tests/security"):
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix == ".pyc" or "__pycache__" in path.parts:
                continue
            if "results" in path.parts and "evals" in path.parts:
                continue  # local eval output, git-ignored
            if ".claude-plugin" in path.parts:
                continue  # the manifest carries the author name the integrator chose
            if path == Path(__file__):
                continue
            for number, line in enumerate(path.read_text().splitlines(), start=1):
                assert not pattern.search(line), f"{path.relative_to(ROOT)}:{number}: {line[:80]}"


def test_scripts_are_executable_and_start_with_a_shebang():
    for script in sorted(PLUGIN.rglob("*.py")):
        assert script.read_text().startswith("#!/usr/bin/env python3"), script.name
        assert script.stat().st_mode & 0o111, f"{script.name} must be executable (chmod +x)"


def _catalog_from_id_list(tmp_path: Path) -> Path:
    """Build a minimal OSCAL-shaped catalog from the reference ID list."""
    groups: dict[str, list[dict[str, str]]] = {}
    for line in (FIXTURES / "sp800-53r5-ids.txt").read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        catalog_id = line.lower().replace("(", ".").rstrip(")")
        groups.setdefault(catalog_id[:2], []).append({"id": catalog_id, "title": line})
    catalog = {
        "catalog": {
            "metadata": {"title": "ids", "version": "0"},
            "groups": [{"id": g, "controls": c} for g, c in groups.items()],
        }
    }
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(catalog))
    return path


def _first_markdown_block(path: Path) -> str:
    match = re.search(r"````markdown\n(.*?)\n````", path.read_text(), re.DOTALL)
    assert match, f"{path.name} has no template block"
    return match.group(1) + "\n"


def test_the_threat_model_template_passes_its_own_checker(tmp_path):
    check = _load("security_doc_check", "scripts/security_doc_check.py")
    doc = tmp_path / "tm.md"
    doc.write_text(_first_markdown_block(PLUGIN / "skills/threat-model/references/template.md"))
    code = check.main(
        [str(doc), "--kind", "threat-model", "--catalog", str(_catalog_from_id_list(tmp_path))]
    )
    assert code == 0


def test_the_compliance_template_passes_once_placeholder_rows_are_removed(tmp_path):
    check = _load("security_doc_check", "scripts/security_doc_check.py")
    text = _first_markdown_block(
        PLUGIN / "skills/compliance-map/references/evidence-map-template.md"
    )
    kept = [line for line in text.splitlines() if not (line.startswith("|") and "<" in line)]
    doc = tmp_path / "cm.md"
    doc.write_text("\n".join(kept) + "\n")
    code = check.main(
        [str(doc), "--kind", "compliance-map", "--catalog", str(_catalog_from_id_list(tmp_path))]
    )
    assert code == 0
