"""Tests for scripts/ticket_state.py: the work-tickets run record."""

from __future__ import annotations

import argparse
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


ticket_state = load_script("ticket_state")


def run(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "ticket_state.py"),
            *args,
            "--data-dir",
            str(tmp_path),
            "--board-key",
            "acme-1",
            "--login",
            "jo",
        ],  # fmt: skip
        capture_output=True,
        text=True,
        check=False,
    )


def slot(number: int, repo: str = "shop-app", slot_id: str = "slot-1") -> str:
    return json.dumps({"slot_id": slot_id, "ticket_number": number, "ticket_repo": repo})


def state_of(tmp_path: Path) -> dict[str, object]:
    return json.loads(run(tmp_path, "show").stdout)


def test_init_creates_an_empty_record(tmp_path: Path) -> None:
    proc = run(tmp_path, "init")
    assert proc.returncode == 0
    path = Path(proc.stdout.strip())
    assert path.name == "ready-worker-acme-1-jo.json"
    assert json.loads(path.read_text())["active"] == []


def test_board_key_with_slashes_becomes_a_safe_file_name() -> None:
    path = ticket_state.state_path(Path("/d"), "group/sub-3", "Jo Smith")
    assert path.name == "ready-worker-group-sub-3-Jo-Smith.json"


def test_begin_then_review_opened_moves_the_slot_to_completed(tmp_path: Path) -> None:
    run(tmp_path, "begin", "--json", slot(7))
    assert len(state_of(tmp_path)["active"]) == 1  # type: ignore[arg-type]
    finish = json.dumps(
        {
            "slot_id": "slot-1",
            "status": "review_opened",
            "review_refs": {"shop-app": "https://x/pr/1"},
        }
    )
    assert run(tmp_path, "finish", "--json", finish).returncode == 0
    state = state_of(tmp_path)
    assert state["active"] == []
    assert state["completed"][0]["review_refs"] == {"shop-app": "https://x/pr/1"}  # type: ignore[index]


@pytest.mark.parametrize(
    "status", ["blocked_tests_failed", "needs_decision", "needs_manual_action"]
)
def test_blocked_results_move_the_slot_to_blocked(tmp_path: Path, status: str) -> None:
    run(tmp_path, "begin", "--json", slot(7))
    run(
        tmp_path,
        "finish",
        "--json",
        json.dumps({"slot_id": "slot-1", "status": status, "reason": "why"}),
    )
    state = state_of(tmp_path)
    assert state["active"] == []
    assert state["blocked"][0]["status"] == status  # type: ignore[index]


def test_running_is_not_a_finished_status(tmp_path: Path) -> None:
    run(tmp_path, "begin", "--json", slot(7))
    proc = run(tmp_path, "finish", "--json", json.dumps({"slot_id": "slot-1", "status": "running"}))
    assert proc.returncode == 2
    assert "not a finished state" in proc.stderr
    assert len(state_of(tmp_path)["active"]) == 1  # type: ignore[arg-type]


def test_same_number_in_two_repos_is_two_tickets(tmp_path: Path) -> None:
    assert run(tmp_path, "begin", "--json", slot(7, "shop-app", "slot-1")).returncode == 0
    assert run(tmp_path, "begin", "--json", slot(7, "api", "slot-2")).returncode == 0


def test_the_same_ticket_cannot_begin_twice(tmp_path: Path) -> None:
    run(tmp_path, "begin", "--json", slot(7))
    proc = run(tmp_path, "begin", "--json", slot(7, slot_id="slot-2"))
    assert proc.returncode == ticket_state.EXIT_REFUSED
    assert "already in active" in proc.stderr


def test_finish_for_an_unknown_slot_is_an_error(tmp_path: Path) -> None:
    proc = run(
        tmp_path, "finish", "--json", json.dumps({"slot_id": "slot-9", "status": "review_opened"})
    )
    assert proc.returncode == 2
    assert "slot-9" in proc.stderr


def test_next_slot_skips_active_and_blocked_slots(tmp_path: Path) -> None:
    assert run(tmp_path, "next-slot").stdout.strip() == "slot-1"
    run(tmp_path, "begin", "--json", slot(1, slot_id="slot-1"))
    run(tmp_path, "begin", "--json", slot(2, slot_id="slot-2"))
    run(tmp_path, "finish", "--json", json.dumps({"slot_id": "slot-1", "status": "needs_decision"}))
    # slot-1 is blocked (keeps its worktree), slot-2 is active
    assert run(tmp_path, "next-slot").stdout.strip() == "slot-3"


def test_skip_is_recorded_once_with_its_latest_reason_and_clears(tmp_path: Path) -> None:
    for reason in ("run:solo", "not groomed"):
        run(tmp_path, "skip", "--number", "60", "--repo", "shop-app", "--reason", reason)
    skipped = state_of(tmp_path)["skipped"]
    assert len(skipped) == 1  # type: ignore[arg-type]
    assert skipped[0]["reason"] == "not groomed"  # type: ignore[index]
    run(tmp_path, "clear-skipped")
    assert state_of(tmp_path)["skipped"] == []


def test_forget_lets_a_ticket_be_retried(tmp_path: Path) -> None:
    run(tmp_path, "begin", "--json", slot(7))
    run(
        tmp_path,
        "finish",
        "--json",
        json.dumps({"slot_id": "slot-1", "status": "blocked_push_rejected"}),
    )
    run(tmp_path, "forget", "--number", "7", "--repo", "shop-app")
    assert state_of(tmp_path)["blocked"] == []
    assert run(tmp_path, "begin", "--json", slot(7)).returncode == 0


def test_set_project_refuses_a_different_assignee(tmp_path: Path) -> None:
    run(tmp_path, "set-project", "--json", json.dumps({"board_key": "acme-1", "assignee": "jo"}))
    proc = run(
        tmp_path, "set-project", "--json", json.dumps({"board_key": "acme-1", "assignee": "sam"})
    )
    assert proc.returncode == ticket_state.EXIT_REFUSED
    assert "assignee" in proc.stderr


def test_unreadable_state_file_names_the_file_and_the_fix(tmp_path: Path) -> None:
    path = Path(run(tmp_path, "init").stdout.strip())
    path.write_text("{ not json", encoding="utf-8")
    proc = run(tmp_path, "show")
    assert proc.returncode == 2
    assert str(path) in proc.stderr
    assert "delete it" in proc.stderr


def test_other_schema_version_is_refused(tmp_path: Path) -> None:
    path = Path(run(tmp_path, "init").stdout.strip())
    path.write_text(json.dumps({"schema_version": 99}), encoding="utf-8")
    proc = run(tmp_path, "show")
    assert proc.returncode == 2
    assert "schema_version" in proc.stderr


def test_missing_option_is_reported(tmp_path: Path) -> None:
    proc = run(tmp_path, "skip", "--number", "1")
    assert proc.returncode == 2
    assert "--repo" in proc.stderr


def test_invalid_json_payload_is_reported(tmp_path: Path) -> None:
    proc = run(tmp_path, "begin", "--json", "{oops")
    assert proc.returncode == 2
    assert "not valid JSON" in proc.stderr


def test_apply_works_in_memory_without_a_file() -> None:
    state = ticket_state.empty_state()
    args = argparse.Namespace(json=slot(3))
    ticket_state.apply(state, "begin", args)
    assert state["active"][0]["status"] == "running"


def test_parallel_writers_lose_no_update(tmp_path: Path) -> None:
    """Six processes begin six tickets at once; the lock must keep every one of them."""
    command = [sys.executable, str(SCRIPTS / "ticket_state.py"), "begin"]
    common = ["--data-dir", str(tmp_path), "--board-key", "acme-1", "--login", "jo"]
    procs = [
        subprocess.Popen(
            [*command, "--json", slot(n, slot_id=f"slot-{n}"), *common],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        for n in range(1, 7)
    ]
    assert [p.wait(timeout=30) for p in procs] == [0] * 6
    numbers = sorted(e["ticket_number"] for e in state_of(tmp_path)["active"])  # type: ignore[attr-defined]
    assert numbers == [1, 2, 3, 4, 5, 6]
