"""The guardrails-help skill and the plugin files stay consistent with the hook."""

from __future__ import annotations

import re
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[2] / "plugins" / "guardrails"
SKILL_DIR = PLUGIN / "skills" / "guardrails-help"
SKILL = SKILL_DIR / "SKILL.md"


def frontmatter(text):
    assert text.startswith("---\n"), "the opening --- must be line 1"
    head, _, body = text[4:].partition("\n---\n")
    fields = {}
    for line in head.splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields, body


def test_frontmatter_follows_the_conventions():
    fields, body = frontmatter(SKILL.read_text())
    assert fields["name"] == "guardrails-help" == SKILL_DIR.name
    assert fields["user-invocable"] == "true"
    assert "disable-model-invocation" not in fields  # Claude may offer it when a block happens
    assert set(fields) <= {"name", "description", "user-invocable"}
    description = fields["description"]
    assert len(description) <= 1024
    assert not description.lower().startswith(("i ", "you "))
    assert "guardrails[" in description  # the trigger a blocked call produces
    assert "claude" not in fields["name"] and "anthropic" not in fields["name"]
    assert len(SKILL.read_text().splitlines()) < 500


def test_skill_matches_the_hook(g):
    text = SKILL.read_text()
    assert f".claude/{g.ALLOW_FILE}" in text
    for rule_id in ("gcp-public-access", "guardrails-tamper", "cannot-decide"):
        assert rule_id in g.RULE_BY_ID  # every rule id the skill names is a real one
        assert rule_id in text
    for rule_id in ("guardrails-tamper", "cannot-decide"):
        assert not g.RULE_BY_ID[rule_id].allowlistable
        assert rule_id in text  # the skill says these two cannot be listed


def test_skill_commands_point_at_a_script_that_exists():
    text = SKILL.read_text()
    assert "${CLAUDE_PLUGIN_ROOT}/hooks/guardrails.py" in text
    assert (PLUGIN / "hooks" / "guardrails.py").exists()
    assert "--list-rules" in text and "--recent" in text


def test_reference_link_resolves():
    text = SKILL.read_text()
    link = re.search(r"\]\((references/[^)]+)\)", text)
    assert link and (SKILL_DIR / link.group(1)).exists()


def test_reference_file_has_a_table_of_contents_when_long():
    ref = (SKILL_DIR / "references" / "rule-sources.md").read_text()
    if len(ref.splitlines()) > 100:
        assert "## Contents" in ref


def test_no_personal_paths_or_secrets_in_plugin_files():
    for path in PLUGIN.rglob("*"):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        text = path.read_text()
        assert "/Users/" not in text, path
        assert not re.search(r"~/[a-z]", text), path
        assert not re.search(r"contrastive|, not (a|an|the) ", text), path
