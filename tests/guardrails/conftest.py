"""Shared fixtures: the hook module, a throwaway git repo, and a subprocess runner.

Everything here is synthetic. Fake credentials in the tests are assembled from pieces at run
time so that no file in this repo contains a literal that a secret scanner would flag.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[2] / "plugins" / "guardrails"
HOOK = PLUGIN / "hooks" / "guardrails.py"


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.test", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


@pytest.fixture(scope="session")
def g():
    """The hook script, imported as a module."""
    spec = importlib.util.spec_from_file_location("guardrails_hook", HOOK)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # dataclasses look the module up by name while the class bodies run
    sys.modules["guardrails_hook"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def repo_template(tmp_path_factory):
    """One repo on branch feature/x, built once and copied for each test."""
    repo = tmp_path_factory.mktemp("template") / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "init")
    _git(repo, "checkout", "-q", "-b", "feature/x")
    (repo / "build").mkdir()
    return repo


@pytest.fixture
def world(tmp_path, repo_template):
    """A repo on branch feature/x, a fake home, and the environment a hook would see."""
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    data = tmp_path / "plugin-data"
    shutil.copytree(repo_template, repo)
    home.mkdir()
    return {
        "repo": repo,
        "home": home,
        "data": data,
        "env": {
            "HOME": str(home),
            "CLAUDE_PROJECT_DIR": str(repo),
            "CLAUDE_PLUGIN_DATA": str(data),
            "CLAUDE_PLUGIN_ROOT": str(PLUGIN),
            "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
        },
    }


@pytest.fixture
def rules_for(g, world):
    """rules_for(tool_name, **tool_input) -> sorted rule ids the hook would raise."""

    def _rules(tool: str, cwd: Path | None = None, **tool_input):
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": tool,
            "tool_input": tool_input,
            "cwd": str(cwd or world["repo"]),
        }
        return sorted({f.rule for f in g.evaluate(payload, world["env"])})

    return _rules


@pytest.fixture
def bash(rules_for):
    """bash("git push origin main") -> rule ids for that Bash command."""
    return lambda command, cwd=None: rules_for("Bash", cwd=cwd, command=command)


@pytest.fixture
def run_hook(world):
    """Run the script as Claude Code does: JSON on stdin, exit code and stderr back."""

    def _run(payload, env=None, python=None):
        raw = payload if isinstance(payload, str) else json.dumps(payload)
        proc = subprocess.run(
            [python or sys.executable, str(HOOK)],
            input=raw,
            capture_output=True,
            text=True,
            env=env if env is not None else world["env"],
            cwd=str(world["repo"]),
        )
        return proc

    return _run
