"""Tests for scripts/waves.py: one test per rule grooming's step 8 relies on."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

SCRIPTS = Path(__file__).resolve().parents[2] / "plugins" / "tickets" / "scripts"


def load_script(name: str) -> ModuleType:
    """Import plugins/tickets/scripts/<name>.py (the scripts are not a package)."""
    spec = importlib.util.spec_from_file_location(f"tickets_{name}", SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"tickets_{name}"] = module
    spec.loader.exec_module(module)
    return module


waves = load_script("waves")


def unit(ref: str, *files: str, title: str = "Fix a thing", labels: tuple[str, ...] = ()) -> dict:
    spans = ", ".join(f"`{f}`" for f in files)
    plan = f"### Final Plan\n\n- **Files to touch**: {spans}\n- **Acceptance**: `make test` passes."
    return {"ref": ref, "title": title, "repo": "acme/app", "labels": list(labels), "plan": plan}


def cut(entries: list[dict], pool: int = waves.DEFAULT_POOL) -> list[list[str]]:
    units = [waves.parse_unit(e) for e in entries]
    return [[u.ref for u in w.units] for w in waves.cut_waves(units, pool)]


def test_units_that_share_a_file_never_share_a_wave() -> None:
    entries = [unit("#1", "src/a.py"), unit("#2", "src/a.py", "src/b.py"), unit("#3", "src/c.py")]
    assert cut(entries) == [["#1", "#3"], ["#2"]]


def test_a_wave_holds_at_most_the_pool_size() -> None:
    entries = [unit(f"#{n}", f"src/{n}.py") for n in range(1, 6)]
    assert cut(entries, pool=2) == [["#1", "#2"], ["#3", "#4"], ["#5"]]


def test_flaky_and_ci_units_come_first() -> None:
    entries = [
        unit("#1", "src/a.py"),
        unit("#2", "src/b.py", title="Quarantine the flaky login test"),
        unit("#3", ".github/workflows/ci.yml", labels=("ci",)),
    ]
    assert cut(entries, pool=2) == [["#2", "#3"], ["#1"]]


def test_a_migration_gets_a_wave_of_its_own() -> None:
    entries = [
        unit("#1", "src/a.py"),
        unit("#2", "migrations/versions/0042_add_owner.py", "src/models.py"),
        unit("#3", "src/b.py", labels=("migration",)),
        unit("#4", "src/c.py"),
    ]
    assert cut(entries) == [["#1", "#4"], ["#2"], ["#3"]]


def test_a_batch_parent_is_one_unit_holding_every_childs_files() -> None:
    parent_plan = (
        "### Final Plan\n\n### #12 Rename the export\n\n- **Files to touch**: `src/export.py`\n"
        "- **Acceptance**: the export test passes.\n\n### #13 Log the export size\n\n"
        "- **Files to touch**: `src/log.py`,\n  `src/size.py`\n- **Acceptance**: a log line.\n"
    )
    batch = {
        "ref": "#20",
        "title": "Batch: export: tidy",
        "repo": "acme/app",
        "plan": parent_plan,
        "children": ["#12", "#13"],
    }
    assert cut([batch, unit("#5", "src/size.py"), unit("#6", "src/other.py")]) == [
        ["#20", "#6"],
        ["#5"],
    ]


def test_a_plan_with_no_files_runs_alone_and_is_reported(tmp_path: Path) -> None:
    vague = unit("#2")
    entries = [unit("#1", "src/a.py"), vague, unit("#3", "src/b.py")]
    path = tmp_path / "units.json"
    path.write_text(json.dumps({"units": entries}), encoding="utf-8")
    run = subprocess.run(
        [sys.executable, str(SCRIPTS / "waves.py"), str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    out = json.loads(run.stdout)
    assert [w["alone"] for w in out["waves"]] == [None, "no files read"]
    assert out["no_files"] == ["#2"]


def test_the_same_input_gives_the_same_waves(tmp_path: Path) -> None:
    # Separate processes, so a set or hash order leaking into the output would show.
    entries = [unit(f"#{n}", f"src/{n % 3}.py", title="CI fix" if n % 2 else "Fix") for n in range(9)]
    path = tmp_path / "units.json"
    path.write_text(json.dumps({"units": entries}), encoding="utf-8")
    runs = {
        subprocess.run(
            [sys.executable, str(SCRIPTS / "waves.py"), str(path), "--pool", "3"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        for _ in range(3)
    }
    assert len(runs) == 1
