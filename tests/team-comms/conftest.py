"""Shared fixtures: load the plugin's scripts by path, since they are not a package."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

PLUGIN = Path(__file__).resolve().parents[2] / "plugins" / "team-comms"


@pytest.fixture(scope="session")
def plugin_dir() -> Path:
    return PLUGIN


@pytest.fixture(scope="session")
def load_script() -> Callable[[str], ModuleType]:
    def load(name: str) -> ModuleType:
        path = PLUGIN / "scripts" / f"{name}.py"
        spec = importlib.util.spec_from_file_location(f"team_comms_{name}", path)
        assert spec and spec.loader, f"cannot load {path}"
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    return load
