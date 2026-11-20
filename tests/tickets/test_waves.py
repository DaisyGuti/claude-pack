"""Tests for scripts/waves.py: one test per rule grooming's step 8 relies on."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tickets_helpers import SCRIPTS, load_script

waves = load_script("waves")


def unit(ref: str, *files: str, title: str = "Fix a thing", labels: tuple[str, ...] = ()) -> dict:
    spans = ", ".join(f"`{f}`" for f in files)
    plan = f"### Final Plan\n\n- **Files to touch**: {spans}\n- **Acceptance**: `make test` passes."
    return {"ref": ref, "title": title, "repo": "acme/app", "labels": list(labels), "plan": plan}


def cut(entries: list[dict], pool: int = 5) -> list[list[str]]:
    units = [waves.parse_unit(e) for e in entries]
    return [[u.ref for u in w.units] for w in waves.cut_waves(units, pool)]


def test_units_that_share_a_file_never_share_a_wave() -> None:
    entries = [unit("#1", "src/a.py"), unit("#2", "src/a.py", "src/b.py"), unit("#3", "src/c.py")]
    assert cut(entries) == [["#1", "#3"], ["#2"]]


def test_a_wave_holds_at_most_the_pool_size() -> None:
    entries = [unit(f"#{n}", f"src/{n}.py") for n in range(1, 6)]
    assert cut(entries, pool=2) == [["#1", "#2"], ["#3", "#4"], ["#5"]]


def test_flaky_and_ci_units_come_first() -> None:
    """No other unit fills a gap in a wave ahead of a flaky-test or CI unit's."""
    entries = [
        unit("#1", "src/c.py"),
        unit("#2", "tests/test_login.py", title="Quarantine the flaky login test"),
        unit("#3", "tests/test_login.py", labels=("ci",)),
        unit("#4", ".github/workflows/ci.yml", labels=("ci",)),
    ]
    assert cut(entries) == [["#2", "#4"], ["#3", "#1"]]


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


def test_files_are_read_as_plans_write_them() -> None:
    """Colon inside the bold, a bare path, a line suffix and a folder all count as files."""
    plan = (
        "### Final Plan\n\n1. **Files to touch:**\n\n   - `src/auth/login.py:12-30`\n"
        "   - docs/guide.md\n2. **Pattern to reuse**: `src/other.py`\n"
    )
    loose = {"ref": "#1", "title": "Fix login", "repo": "acme/app", "plan": plan}
    assert waves.files_to_touch(plan) == [(None, "src/auth/login.py"), (None, "docs/guide.md")]
    assert cut([loose, unit("#2", "src/auth/"), unit("#3", "src/other.py")]) == [
        ["#1", "#3"],
        ["#2"],
    ]


def test_bad_input_exits_2(tmp_path: Path) -> None:
    path = tmp_path / "units.json"
    path.write_text(json.dumps({"units": [unit("#1", "a/b.py"), unit("#1", "a/c.py")]}))
    run = subprocess.run(
        [sys.executable, str(SCRIPTS / "waves.py"), str(path), "--pool", "5"],
        capture_output=True,
        text=True,
    )
    assert run.returncode == 2 and "#1" in run.stderr


def test_a_plan_with_no_files_runs_alone_and_is_reported(tmp_path: Path) -> None:
    vague = unit("#2")
    entries = [unit("#1", "src/a.py"), vague, unit("#3", "src/b.py")]
    path = tmp_path / "units.json"
    path.write_text(json.dumps({"units": entries}), encoding="utf-8")
    run = subprocess.run(
        [sys.executable, str(SCRIPTS / "waves.py"), str(path), "--pool", "5"],
        capture_output=True,
        text=True,
        check=True,
    )
    out = json.loads(run.stdout)
    assert [w["alone"] for w in out["waves"]] == [None, "no files read"]
    assert out["no_files"] == ["#2"]


def test_the_same_input_gives_the_same_waves(tmp_path: Path) -> None:
    # Separate processes, so a set or hash order leaking into the output would show.
    titles = ("Fix", "CI fix")
    entries = [unit(f"#{n}", f"src/{n % 3}.py", title=titles[n % 2]) for n in range(9)]
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


def plan_with(files: str) -> dict:
    plan = f"### Final Plan\n\n- **Files to touch**: {files}\n- **Acceptance**: done."
    return {"ref": "#9", "title": "Fix a thing", "repo": "acme/app", "plan": plan}


def test_a_repo_qualified_path_belongs_to_that_repo() -> None:
    entry = plan_with("`other: src/a.py`, `acme/third: src/b.py`, `src/c.py`")
    assert waves.parse_unit(entry).files == {
        ("acme/other", "src/a.py"),
        ("acme/third", "src/b.py"),
        ("acme/app", "src/c.py"),
    }


def test_a_unit_in_another_repo_does_not_collide_on_the_same_path() -> None:
    mine, theirs = unit("#1", "src/a.py"), plan_with("`other: src/a.py`")
    assert cut([mine, theirs]) == [["#1", "#9"]]


def test_only_flaky_or_broken_ci_titles_come_first() -> None:
    def first(title: str) -> bool:
        return waves.parse_unit({**unit("#1", "a/b.py"), "title": title}).first

    assert first("Document the CI/CD pipeline") is False
    assert first("Investigate login test flakiness") is True
    assert first("Fix the CI build") is True


def test_a_scoped_label_counts_by_its_last_part() -> None:
    assert waves.parse_unit(unit("#1", "a/b.py", labels=("type:flaky-test",))).first


def test_url_fragments_and_plain_backticked_words_are_not_files() -> None:
    entry = plan_with("see example.com/y and `pytest`, `make test`, then `src/a.py`")
    assert waves.files_to_touch(entry["plan"]) == [(None, "src/a.py")]


def test_root_files_and_noted_paths_still_count() -> None:
    entry = plan_with(
        "`Makefile`, `.gitignore`, `src/b.py: see docs/x.md`, "
        "`Acme/Other: src/c.py`, `other: LICENSE`"
    )
    assert waves.parse_unit(entry).files == {
        ("acme/app", "Makefile"),
        ("acme/app", ".gitignore"),
        ("acme/app", "src/b.py"),
        ("acme/other", "src/c.py"),
        ("acme/other", "LICENSE"),
        ("acme/app", "docs/x.md"),
    }
