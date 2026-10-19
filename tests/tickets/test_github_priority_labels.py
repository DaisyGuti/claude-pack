"""The GitHub adapter reads priority from labels on a board in label mode, and only there.

The adapter is Markdown a skill executes, so this test lifts the `list-items` jq filter
out of `references/trackers/github.md`, fills in the priority array the way the doc says
for each mode, and runs it with `jq` over a sample `gh project item-list` payload.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ADAPTER = (
    Path(__file__).resolve().parents[2]
    / "plugins"
    / "tickets"
    / "references"
    / "trackers"
    / "github.md"
)
PRIORITIES = ["P0", "P1", "P2", "P3"]
PLACEHOLDER = '["<every priority value, in rank order>"]'

pytestmark = pytest.mark.skipif(shutil.which("jq") is None, reason="jq is not installed")


def list_items_program() -> str:
    """The jq program passed to `--jq` in list-items, placeholder still in it."""
    text = ADAPTER.read_text(encoding="utf-8")
    start = text.index("## list-items\n")
    body = text[start : text.index("\n## ", start + 1)]
    match = re.search(r"--jq '(.*?)'\n```", body, re.S)
    assert match, "list-items no longer passes a single-quoted --jq program"
    assert PLACEHOLDER in match.group(1), "list-items lost its priority-array placeholder"
    return match.group(1)


def item(number: int, *, priority: str | None, labels: list[str]) -> dict:
    return {
        "id": f"PVTI_{number}",
        "content": {"number": number, "repository": "acme/app", "type": "Issue"},
        "title": f"ticket {number}",
        "status": "Ready",
        "priority": priority,
        "labels": labels,
        "assignees": ["someone"],
    }


PAYLOAD = {
    "items": [
        item(1, priority=None, labels=["bug", "P2", "P1"]),
        item(2, priority="P3", labels=["P0"]),
        item(3, priority=None, labels=["enhancement"]),
        item(4, priority=None, labels=["High"]),
    ]
}


def run(priority_array: list[str]) -> dict[int, dict]:
    program = list_items_program().replace(PLACEHOLDER, json.dumps(priority_array))
    out = subprocess.run(
        ["jq", "-c", program],
        input=json.dumps(PAYLOAD),
        capture_output=True,
        text=True,
        check=True,
    )
    return {row["number"]: row for row in map(json.loads, out.stdout.splitlines())}


def test_label_mode_takes_priority_from_the_highest_ranked_label() -> None:
    rows = run(PRIORITIES)
    assert rows[1]["priority"] == "P1", "the highest-ranked priority label wins"
    assert rows[2]["priority"] == "P3", "a set Priority field still wins over labels"
    assert rows[3]["priority"] is None, "no priority label means unset"
    assert rows[4]["priority"] is None, "a label outside the registry values is not a priority"
    assert rows[1]["labels"] == ["bug", "P2", "P1"]
    assert rows[1]["type"] == "issue"


def test_field_mode_ignores_priority_labels() -> None:
    rows = run([])
    assert rows[1]["priority"] is None, "an empty field stays empty in field mode"
    assert rows[2]["priority"] == "P3"
    assert rows[1]["labels"] == ["bug", "P2", "P1"]
