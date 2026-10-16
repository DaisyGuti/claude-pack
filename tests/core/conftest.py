"""Shared fixtures for the core plugin tests: script loaders and synthetic git repos."""

from __future__ import annotations

import importlib.util
import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

PLUGIN = Path(__file__).resolve().parents[2] / "plugins" / "core"
SCRIPTS = PLUGIN / "skills" / "project-setup" / "scripts"


def load_script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader, f"cannot load {name}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def scan_repo() -> ModuleType:
    return load_script("scan_repo")


@pytest.fixture(scope="session")
def check_claude_md() -> ModuleType:
    return load_script("check_claude_md")


GIT_ENV = {
    "GIT_AUTHOR_NAME": "Test Author",
    "GIT_AUTHOR_EMAIL": "author@example.invalid",
    "GIT_COMMITTER_NAME": "Test Author",
    "GIT_COMMITTER_EMAIL": "author@example.invalid",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
}


def run_git(repo: Path, *args: str) -> None:
    env = {**os.environ, **GIT_ENV}
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=env)


@pytest.fixture(autouse=True)
def isolated_git_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the tester's own git config (signing, hooks, templates) out of every test."""
    for key, value in GIT_ENV.items():
        monkeypatch.setenv(key, value)


@pytest.fixture
def make_repo(tmp_path: Path) -> Callable[..., Path]:
    """Build a synthetic repo: files maps relative path to text; messages are commit subjects."""

    def build(
        files: dict[str, str] | None = None,
        messages: tuple[str, ...] = ("feat: first commit",),
        remote: str | None = None,
    ) -> Path:
        repo = tmp_path / "repo"
        repo.mkdir()
        run_git(repo, "init", "-q", "-b", "main")
        for rel, text in (files or {}).items():
            target = repo / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        run_git(repo, "add", "-A")
        for message in messages:
            run_git(repo, "commit", "-q", "--allow-empty", "-m", message)
        if remote:
            run_git(repo, "remote", "add", "origin", remote)
        return repo

    return build
