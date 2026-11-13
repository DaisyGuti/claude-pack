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


def test_finish_keeps_the_follow_up_refs_a_worker_reports(tmp_path: Path) -> None:
    """A worker's RESULT carries the follow-up tickets it filed; the record keeps them as sent."""
    run(tmp_path, "begin", "--json", slot(7))
    refs = [
        {
            "repo": "shop-app",
            "number": 201,
            "title": "t",
            "url": "https://x/i/201",
            "action": "filed",
        },
        {"repo": "shop-app", "number": None, "title": "u", "url": None, "action": "not_filed"},
    ]
    finish = json.dumps({"slot_id": "slot-1", "status": "review_opened", "follow_up_refs": refs})
    assert run(tmp_path, "finish", "--json", finish).returncode == 0
    assert state_of(tmp_path)["completed"][0]["follow_up_refs"] == refs  # type: ignore[index]


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


def batch(
    children: list[int], parent: str = "341", slot_id: str = "slot-1", repo: str = "shop-app"
) -> str:
    """A batch slot: the first child names it, and it claims every child and its parent."""
    return json.dumps(
        {
            "slot_id": slot_id,
            "ticket_number": children[0],
            "ticket_repo": repo,
            "parent": {"ref": parent, "repo": repo},
            "children": [{"ticket_number": n, "ticket_repo": repo} for n in children],
        }
    )


def test_a_batch_slot_claims_every_child(tmp_path: Path) -> None:
    assert run(tmp_path, "begin", "--json", batch([7, 8, 9])).returncode == 0
    proc = run(tmp_path, "begin", "--json", slot(8, slot_id="slot-2"))
    assert proc.returncode == ticket_state.EXIT_REFUSED
    assert "shop-app#8 is already in active" in proc.stderr


def test_a_batch_slot_is_refused_when_a_child_is_already_tracked(tmp_path: Path) -> None:
    run(tmp_path, "begin", "--json", slot(9))
    proc = run(tmp_path, "begin", "--json", batch([7, 9], slot_id="slot-2"))
    assert proc.returncode == ticket_state.EXIT_REFUSED
    assert "shop-app#9 is already in active" in proc.stderr
    assert len(state_of(tmp_path)["active"]) == 1  # type: ignore[arg-type]


def test_one_active_slot_per_parent_and_a_finished_parent_takes_a_later_batch(
    tmp_path: Path,
) -> None:
    run(tmp_path, "begin", "--json", batch([7, 8]))
    proc = run(tmp_path, "begin", "--json", batch([9], slot_id="slot-2"))
    assert proc.returncode == ticket_state.EXIT_REFUSED
    assert "batch parent 341 is already in active slot slot-1" in proc.stderr
    finish = json.dumps({"slot_id": "slot-1", "status": "review_opened"})
    assert run(tmp_path, "finish", "--json", finish).returncode == 0
    assert run(tmp_path, "begin", "--json", batch([9], slot_id="slot-2")).returncode == 0


def test_finish_keeps_the_children_a_batch_slot_began_with(tmp_path: Path) -> None:
    """The worker's per-child outcome rides along; what the slot claims does not change."""
    run(tmp_path, "begin", "--json", batch([7, 8]))
    outcome = [
        {"ticket_number": 7, "ticket_repo": "shop-app", "status": "review_opened"},
        {"ticket_number": 8, "ticket_repo": "shop-app", "status": "blocked_tests_failed"},
    ]
    finish = json.dumps(
        {"slot_id": "slot-1", "status": "review_opened", "children": [], "children_status": outcome}
    )
    assert run(tmp_path, "finish", "--json", finish).returncode == 0
    entry = state_of(tmp_path)["completed"][0]  # type: ignore[index]
    assert [c["ticket_number"] for c in entry["children"]] == [7, 8]
    assert entry["children_status"] == outcome
    assert run(tmp_path, "begin", "--json", slot(8, slot_id="slot-2")).returncode == 3


def test_forget_frees_one_child_and_drops_the_slot_with_its_last(tmp_path: Path) -> None:
    run(tmp_path, "begin", "--json", batch([7, 8]))
    run(tmp_path, "finish", "--json", json.dumps({"slot_id": "slot-1", "status": "review_opened"}))
    run(tmp_path, "forget", "--number", "8", "--repo", "shop-app")
    completed = state_of(tmp_path)["completed"]
    assert [c["ticket_number"] for c in completed[0]["children"]] == [7]  # type: ignore[index]
    assert run(tmp_path, "begin", "--json", slot(8, slot_id="slot-2")).returncode == 0
    run(tmp_path, "forget", "--number", "7", "--repo", "shop-app")
    assert state_of(tmp_path)["completed"] == []


@pytest.mark.parametrize(
    "payload",
    [
        {"slot_id": "slot-1", "ticket_number": 7, "ticket_repo": "r", "children": []},
        {"slot_id": "slot-1", "ticket_number": 7, "ticket_repo": "r", "children": [{"x": 1}]},
        {"slot_id": "slot-1", "ticket_number": 7, "ticket_repo": "r", "parent": {"ref": "1"}},
    ],
)
def test_a_malformed_batch_slot_is_bad_input(tmp_path: Path, payload: dict[str, object]) -> None:
    assert run(tmp_path, "begin", "--json", json.dumps(payload)).returncode == 2
    assert state_of(tmp_path)["active"] == []


def test_forgetting_the_first_child_moves_the_slot_to_the_next_child(tmp_path: Path) -> None:
    run(tmp_path, "begin", "--json", batch([7, 8, 9]))
    run(tmp_path, "finish", "--json", json.dumps({"slot_id": "slot-1", "status": "review_opened"}))
    assert run(tmp_path, "forget", "--number", "7", "--repo", "shop-app").returncode == 0
    entry = state_of(tmp_path)["completed"][0]  # type: ignore[index]
    assert (entry["ticket_number"], entry["ticket_repo"]) == (8, "shop-app")
    assert [c["ticket_number"] for c in entry["children"]] == [8, 9]
    assert run(tmp_path, "begin", "--json", slot(7, slot_id="slot-2")).returncode == 0
    # Forgetting the next child frees it in turn, though it now names the slot.
    assert run(tmp_path, "forget", "--number", "8", "--repo", "shop-app").returncode == 0
    entry = state_of(tmp_path)["completed"][0]  # type: ignore[index]
    assert entry["ticket_number"] == 9
    assert run(tmp_path, "begin", "--json", slot(8, slot_id="slot-3")).returncode == 0


def test_forgetting_every_child_lets_the_same_slot_begin_again(tmp_path: Path) -> None:
    """The signing-key resume: forget each child, then begin the slot under its own id."""
    run(tmp_path, "begin", "--json", batch([7, 8]))
    stop = {"slot_id": "slot-1", "status": "blocked_sandbox", "reason": "signing key locked"}
    assert run(tmp_path, "finish", "--json", json.dumps(stop)).returncode == 0
    for number in ("7", "8"):
        assert run(tmp_path, "forget", "--number", number, "--repo", "shop-app").returncode == 0
    assert state_of(tmp_path)["blocked"] == []
    assert run(tmp_path, "begin", "--json", batch([7, 8])).returncode == 0
    active = state_of(tmp_path)["active"]
    assert [(e["slot_id"], e["ticket_number"]) for e in active] == [("slot-1", 7)]  # type: ignore[index]


def test_a_batch_slot_is_refused_only_for_its_active_parent(tmp_path: Path) -> None:
    """No child is shared: the refusal names the parent's active slot, and nothing is added."""
    run(tmp_path, "begin", "--json", batch([7, 8]))
    proc = run(tmp_path, "begin", "--json", batch([9, 10], slot_id="slot-2"))
    assert proc.returncode == ticket_state.EXIT_REFUSED
    assert "batch parent 341 is already in active slot slot-1" in proc.stderr
    assert "shop-app#" not in proc.stderr  # no child is named: none is tracked
    assert [e["slot_id"] for e in state_of(tmp_path)["active"]] == ["slot-1"]  # type: ignore[index]
    # The same children under another parent begin: only the parent was in the way.
    assert run(tmp_path, "begin", "--json", batch([9, 10], "342", "slot-2")).returncode == 0
