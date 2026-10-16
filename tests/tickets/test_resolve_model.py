"""Tests for scripts/resolve_model.py: ticket labels to a Claude model alias."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

PLUGIN = Path(__file__).resolve().parents[2] / "plugins" / "tickets"
SCRIPTS = PLUGIN / "scripts"


def load_script(name: str) -> ModuleType:
    """Import plugins/tickets/scripts/<name>.py (the scripts are not a package)."""
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(f"tickets_{name}", SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"tickets_{name}"] = module
    spec.loader.exec_module(module)
    return module


resolve_model = load_script("resolve_model")


@pytest.mark.parametrize(
    ("label", "tier", "model"),
    [
        ("model:haiku", "fast", "haiku"),
        ("model:sonnet", "workhorse", "sonnet"),
        ("model:opus", "frontier", "opus"),
        ("model:fast", "fast", "haiku"),
        ("model:workhorse", "workhorse", "sonnet"),
        ("model:frontier", "frontier", "opus"),
        ("model:claude-sonnet-4-5", "workhorse", "sonnet"),
        ("model:claude-opus", "frontier", "opus"),
    ],
)
def test_known_labels_resolve_without_a_registry(label: str, tier: str, model: str) -> None:
    code, payload = resolve_model.resolve(["bug", label], {})
    assert code == 0
    assert (payload["tier"], payload["model"], payload["effort"]) == (tier, model, None)


def test_registry_table_maps_a_custom_label() -> None:
    code, payload = resolve_model.resolve(["model:small"], {"model:small": "fast"})
    assert (code, payload["model"]) == (0, "haiku")


def test_no_model_label_exits_3() -> None:
    code, payload = resolve_model.resolve(["bug", "P1"], {})
    assert code == resolve_model.EXIT_NO_LABEL
    assert "no model label" in payload["error"]


def test_labels_for_different_tiers_conflict() -> None:
    code, payload = resolve_model.resolve(["model:haiku", "model:opus"], {})
    assert code == resolve_model.EXIT_CONFLICT
    assert "model:haiku" in payload["error"]


def test_two_labels_for_one_tier_are_not_a_conflict() -> None:
    code, payload = resolve_model.resolve(["model:sonnet", "model:workhorse"], {})
    assert (code, payload["tier"]) == (0, "workhorse")


def test_unrecognized_model_label_exits_5() -> None:
    code, payload = resolve_model.resolve(["model:gpt"], {})
    assert code == resolve_model.EXIT_UNRECOGNIZED
    assert "model:gpt" in payload["error"]


def test_effort_label_is_passed_through_when_valid() -> None:
    _, payload = resolve_model.resolve(["model:opus", "effort:xhigh"], {})
    assert payload["effort"] == "xhigh"


def test_invalid_effort_label_is_ignored() -> None:
    _, payload = resolve_model.resolve(["model:opus", "effort:extreme"], {})
    assert payload["effort"] is None


def test_command_line_reads_the_registry_table(filled_registry: Path) -> None:
    path = filled_registry / "registry.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace("`model:haiku`", "`model:tiny`"), encoding="utf-8"
    )
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "resolve_model.py"), "--registry", str(path), "model:tiny"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["model"] == "haiku"


def test_tier_flag_prints_the_alias() -> None:
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "resolve_model.py"), "--tier", "frontier"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert json.loads(proc.stdout)["model"] == "opus"


def test_missing_registry_file_names_the_fix(tmp_path: Path) -> None:
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "resolve_model.py"),
            "--registry",
            str(tmp_path / "x.md"),
            "model:opus",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 2
    assert "registry.py ensure" in proc.stderr


def test_registry_label_without_the_model_prefix_still_counts() -> None:
    code, payload = resolve_model.resolve(["ai:cheap", "bug"], {"ai:cheap": "fast"})
    assert (code, payload["model"]) == (0, "haiku")
