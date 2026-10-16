"""The README names every plugin, skill and agent, and every relative link resolves."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
README = (ROOT / "README.md").read_text(encoding="utf-8")
PLUGINS = sorted(p.name for p in (ROOT / "plugins").iterdir() if p.is_dir())


def skills_of(plugin: str) -> list[str]:
    return sorted(p.parent.name for p in (ROOT / "plugins" / plugin).glob("skills/*/SKILL.md"))


def agents_of(plugin: str) -> list[str]:
    return sorted(p.stem for p in (ROOT / "plugins" / plugin).glob("agents/*.md"))


@pytest.mark.parametrize("plugin", PLUGINS)
def test_plugin_is_in_the_catalog(plugin: str) -> None:
    assert f"[`{plugin}`](plugins/{plugin})" in README


@pytest.mark.parametrize("plugin", PLUGINS)
def test_every_skill_and_agent_has_its_invoke_name(plugin: str) -> None:
    missing = [f"/{plugin}:{s}" for s in skills_of(plugin) if f"`/{plugin}:{s}`" not in README]
    missing += [
        f"@agent-{plugin}:{a}" for a in agents_of(plugin) if f"`@agent-{plugin}:{a}`" not in README
    ]
    assert not missing, missing


def test_marketplace_lists_the_same_plugins_as_the_folders() -> None:
    manifest = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
    assert sorted(p["name"] for p in manifest["plugins"]) == PLUGINS


def test_relative_links_resolve() -> None:
    broken = []
    for target in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", README):
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        if not (ROOT / target).exists():
            broken.append(target)
    assert not broken, broken
