"""Tests for scripts/deps.py: one test per finding grooming's step 3 and planning rely on."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tickets_helpers import SCRIPTS, load_script

deps = load_script("deps")


def ticket(ref: str, body: str = "", state: str = "open") -> dict:
    return {"ref": ref, "repo": "acme/app", "state": state, "title": "A ticket", "body": body}


def part(n: int, tracker: str = "#21", body: str = "") -> str:
    return f"## Context\n\nPart {n} of 3, cut by layer from {tracker} (too big).\n{body}"


def run(entries: list[dict]) -> dict:
    tickets = [deps.parse_ticket(e) for e in entries]
    return deps.report(deps.build_board(tickets))


def run_script(tmp_path: Path, data: object) -> subprocess.CompletedProcess[str]:
    path = tmp_path / "tickets.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "deps.py"), str(path)], capture_output=True, text=True
    )


# The board grooming found: #26 waits on the tracker #21, which closes after its parts, and two
# of those parts wait on #26.
CIRCULAR_BOARD = [
    ticket("#21", "Cut into parts."),
    ticket("#26", "Depends on: #21"),
    ticket("#31", part(1), state="closed"),
    ticket("#32", part(2, body="Depends on: #26")),
    ticket("#33", part(3, "https://git.example.com/acme/app/-/issues/21", "Depends on: #26")),
]


def test_a_chain_back_to_the_ticket_is_a_cycle() -> None:
    cycles = run(CIRCULAR_BOARD)["cycles"]
    assert cycles == [
        [
            {"from": "acme/app#21", "to": "acme/app#32", "via": "part"},
            {"from": "acme/app#32", "to": "acme/app#26", "via": "depends on"},
            {"from": "acme/app#26", "to": "acme/app#21", "via": "depends on"},
        ]
    ]


def test_naming_a_tracker_points_to_its_open_part() -> None:
    board = [
        ticket("#21"),
        ticket("#26", "Blocked by: acme/app#21"),
        ticket("#31", part(1), state="closed"),
        ticket("#32", part(2)),
    ]
    assert run(board)["tracker_dependencies"] == [
        {
            "ticket": "acme/app#26",
            "names": "acme/app#21",
            "kind": "tracker",
            "open_parts": ["acme/app#32"],
            "name_instead": "acme/app#32",
        }
    ]


def test_naming_a_batch_parent_lists_its_open_children_to_choose_from() -> None:
    board = [
        {**ticket("#40"), "children": ["#41", "#42"]},
        ticket("#41"),
        ticket("#42"),
        ticket("#50", "Depends on: app#40"),
    ]
    (found,) = run(board)["tracker_dependencies"]
    assert found["kind"] == "batch parent"
    assert found["open_parts"] == ["acme/app#41", "acme/app#42"]
    assert found["name_instead"] is None


def test_an_open_dependency_whose_work_merged_is_reported() -> None:
    review = "https://git.example.com/acme/app/-/merge_requests/73"
    board = [{**ticket("#13"), "merged_reviews": [review]}, ticket("#60", "Depends on: #13")]
    assert run(board)["merged_dependencies"] == [
        {"ticket": "acme/app#60", "names": "acme/app#13", "reviews": [review]}
    ]


def test_a_hold_clears_only_when_every_dependency_is_closed_and_known() -> None:
    board = [
        ticket("#11", state="closed"),
        ticket("#12"),
        ticket("#70", "Depends on: #11"),
        ticket("#71", "Depends on: #11, #12"),
        ticket("#72", "Depends on: #11 and other/lib#5"),
    ]
    out = run(board)
    assert out["cleared"] == [{"ticket": "acme/app#70", "depends_on": ["acme/app#11"]}]
    assert out["unknown"] == ["other/lib#5"]


def test_refs_in_urls_and_reviews_are_read_as_tickets_write_them() -> None:
    """A GitLab work item URL counts; a merge request URL, `!4` and a heading do not."""
    body = (
        "## Context\nDepends on: https://git.example.com/acme/app/-/work_items/8, "
        "https://git.example.com/acme/app/-/merge_requests/9, !4, lib#3"
    )
    assert deps.parse_ticket(ticket("#1", body)).depends_on == ("acme/app#8", "acme/lib#3")


def test_bad_input_exits_2(tmp_path: Path) -> None:
    result = run_script(tmp_path, {"tickets": [ticket("#1"), ticket("#1")]})
    assert result.returncode == 2 and "acme/app#1" in result.stderr
    assert run_script(tmp_path, {"tickets": [ticket("#1", state="done")]}).returncode == 2


def test_the_same_board_gives_the_same_report(tmp_path: Path) -> None:
    # Separate processes, so a set or hash order leaking into the output would show.
    outputs = {run_script(tmp_path, {"tickets": CIRCULAR_BOARD}).stdout for _ in range(3)}
    assert len(outputs) == 1 and json.loads(outputs.pop())["cycles"]
