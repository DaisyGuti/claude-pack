"""Shared fixtures for the tickets plugin tests."""

from __future__ import annotations

from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[2] / "plugins" / "tickets"


@pytest.fixture
def filled_registry(tmp_path: Path) -> Path:
    """A registry.md copied from the example with a real clone folder and no example values."""
    clone = tmp_path / "code" / "shop-app"
    clone.mkdir(parents=True)
    text = (PLUGIN / "registry.example.md").read_text(encoding="utf-8")
    text = text.replace("your-github-login/my-app", "acme/shop-app")
    text = text.replace("your-github-login", "acme")
    text = text.replace("your-group", "acme-team")
    text = text.replace("`my-app`", "`shop-app`")
    text = text.replace("~/code/my-app/README.md", f"{clone}/README.md")
    text = text.replace("~/code/my-app", str(clone))
    data = tmp_path / "data"
    data.mkdir()
    (data / "registry.md").write_text(text, encoding="utf-8")
    return data
