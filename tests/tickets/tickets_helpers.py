"""Shared by the tickets tests: load a plugin script by name (the scripts are not a package).

Import it as `from tickets_helpers import load_script`; conftest.py puts this folder on sys.path,
which `--import-mode=importlib` does not do.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

SCRIPTS = Path(__file__).resolve().parents[2] / "plugins" / "tickets" / "scripts"


def load_script(name: str) -> ModuleType:
    """Import plugins/tickets/scripts/<name>.py as `tickets_<name>`."""
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(f"tickets_{name}", SCRIPTS / f"{name}.py")
    assert spec and spec.loader, f"cannot load {name}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
