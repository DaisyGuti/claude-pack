"""Structural checks for the ui-design plugin's skills: size limits and links that resolve."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[2] / "plugins/ui-design"
SKILLS = sorted(p.parent for p in PLUGIN.glob("skills/*/SKILL.md"))
# Skill text may point at its bundled files by variable or by relative markdown link.
VARIABLE_PATH = re.compile(r"\$\{CLAUDE_SKILL_DIR\}/([\w./-]+)")
MARKDOWN_LINK = re.compile(r"\]\((?!https?:|#|mailto:)([^)#\s]+)")
# Anthropic's limits: SKILL.md under 500 lines;
# description plus when_to_use at most 1,536 characters.
MAX_LINES = 500
MAX_LISTING_CHARS = 1536


def frontmatter(skill: Path) -> dict[str, str]:
    text = (skill / "SKILL.md").read_text()
    block = text.split("---")[1]
    fields: dict[str, str] = {}
    for line in block.splitlines():
        match = re.match(r"^([\w-]+):\s*(.*)$", line)
        if match:
            fields[match[1]] = match[2]
    return fields


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.name)
def test_skill_name_matches_folder_and_limits_hold(skill: Path) -> None:
    fields = frontmatter(skill)
    assert fields["name"] == skill.name
    listing = len(fields["description"]) + len(fields.get("when_to_use", ""))
    assert listing <= MAX_LISTING_CHARS, f"description is {listing} characters"
    assert len((skill / "SKILL.md").read_text().splitlines()) < MAX_LINES


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.name)
def test_bundled_paths_in_skill_text_exist(skill: Path) -> None:
    missing: list[str] = []
    for doc in [skill / "SKILL.md", *sorted(skill.glob("references/*.md"))]:
        text = doc.read_text()
        for relative in VARIABLE_PATH.findall(text):
            if not (skill / relative.rstrip(".")).exists():
                missing.append(f"{doc.name}: ${{CLAUDE_SKILL_DIR}}/{relative}")
        for relative in MARKDOWN_LINK.findall(text):
            if not (doc.parent / relative).resolve().exists():
                missing.append(f"{doc.name}: {relative}")
    assert not missing, missing
