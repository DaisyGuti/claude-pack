"""Tests for scripts/slack_helpers.py: time windows and permalinks on fixed clocks."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

NY = ZoneInfo("America/New_York")
# 2026-10-14 is a Wednesday.
WEDNESDAY = datetime(2026, 10, 14, 9, 30, tzinfo=NY)
MONDAY = datetime(2026, 10, 12, 9, 30, tzinfo=NY)
SUNDAY = datetime(2026, 10, 18, 9, 30, tzinfo=NY)


@pytest.fixture
def helpers(load_script):
    return load_script("slack_helpers")


@pytest.mark.parametrize(
    ("spec", "now", "expected"),
    [
        ("yesterday", WEDNESDAY, datetime(2026, 10, 13, 0, 0, tzinfo=NY)),
        ("today", WEDNESDAY, datetime(2026, 10, 14, 0, 0, tzinfo=NY)),
        ("last-workday", WEDNESDAY, datetime(2026, 10, 13, 0, 0, tzinfo=NY)),
        ("last-workday", MONDAY, datetime(2026, 10, 9, 0, 0, tzinfo=NY)),
        ("last-workday", SUNDAY, datetime(2026, 10, 16, 0, 0, tzinfo=NY)),
        ("monday", WEDNESDAY, datetime(2026, 10, 12, 0, 0, tzinfo=NY)),
        ("monday", MONDAY, datetime(2026, 10, 5, 0, 0, tzinfo=NY)),
        ("3d", WEDNESDAY, datetime(2026, 10, 11, 9, 30, tzinfo=NY)),
        ("6h", WEDNESDAY, datetime(2026, 10, 14, 3, 30, tzinfo=NY)),
        ("2026-10-01", WEDNESDAY, datetime(2026, 10, 1, 0, 0, tzinfo=NY)),
        ("2026-10-13T14:15", WEDNESDAY, datetime(2026, 10, 13, 14, 15, tzinfo=NY)),
    ],
)
def test_resolve_since(helpers, spec: str, now: datetime, expected: datetime) -> None:
    assert helpers.resolve_since(spec, now) == expected


def test_since_report_gives_oldest_and_search_date(helpers) -> None:
    report = helpers.since_report("yesterday", WEDNESDAY)
    assert float(report["oldest"]) == datetime(2026, 10, 13, 0, 0, tzinfo=NY).timestamp()
    assert report["search_after"] == "2026-10-12"
    assert report["oldest_iso"].startswith("2026-10-13T00:00")


def test_future_start_is_refused(helpers) -> None:
    with pytest.raises(helpers.InputError, match="future"):
        helpers.since_report("2026-12-01", WEDNESDAY)


def test_unreadable_spec_names_the_input_and_the_fix(helpers) -> None:
    with pytest.raises(helpers.InputError) as err:
        helpers.resolve_since("sometime soon", WEDNESDAY)
    assert "sometime soon" in str(err.value)
    assert "YYYY-MM-DD" in str(err.value)


def test_unknown_zone_is_refused(helpers) -> None:
    with pytest.raises(helpers.InputError, match="IANA"):
        helpers.zone("Mars/Olympus")


@pytest.mark.parametrize("workspace", ["acme", "acme.slack.com", "https://acme.slack.com/x/y"])
def test_workspace_forms_normalize(helpers, workspace: str) -> None:
    assert helpers.workspace_host(workspace) == "acme.slack.com"


def test_permalink_for_a_channel_message(helpers) -> None:
    url = helpers.permalink("acme", "C0123456789", "1760000000.000200")
    assert url == "https://acme.slack.com/archives/C0123456789/p1760000000000200"


def test_permalink_for_a_thread_reply(helpers) -> None:
    url = helpers.permalink("acme", "C0123456789", "1760000100.000300", "1760000000.000200")
    assert url == (
        "https://acme.slack.com/archives/C0123456789/p1760000100000300"
        "?thread_ts=1760000000.000200&cid=C0123456789"
    )


def test_permalink_to_the_thread_root_has_no_query(helpers) -> None:
    ts = "1760000000.000200"
    assert "?" not in helpers.permalink("acme", "C0123456789", ts, ts)


@pytest.mark.parametrize(
    ("channel", "ts"),
    [("general", "1760000000.000200"), ("C0123456789", "1760000000"), ("C0123456789", "x.y")],
)
def test_bad_ids_are_refused(helpers, channel: str, ts: str) -> None:
    with pytest.raises(helpers.InputError):
        helpers.permalink("acme", channel, ts)


def run_cli(*args: str, stdin: str = "") -> subprocess.CompletedProcess[str]:
    script = Path(__file__).resolve().parents[2] / "plugins/team-comms/scripts/slack_helpers.py"
    return subprocess.run(
        [sys.executable, str(script), *args], input=stdin, capture_output=True, text=True
    )


def test_cli_since_prints_json() -> None:
    result = run_cli("since", "yesterday", "--tz", "America/New_York", "--now", "2026-10-14T09:30")
    assert result.returncode == 0
    assert json.loads(result.stdout)["search_after"] == "2026-10-12"


def test_cli_permalink_batch() -> None:
    batch = json.dumps(
        [
            {"channel": "C0123456789", "ts": "1760000000.000200"},
            {"channel": "C0123456789", "ts": "1760000100.000300", "thread_ts": "1760000000.000200"},
        ]
    )
    result = run_cli("permalink", "--workspace", "acme", "--batch", stdin=batch)
    assert result.returncode == 0
    urls = [item["url"] for item in json.loads(result.stdout)]
    assert urls[0].endswith("/p1760000000000200")
    assert urls[1].endswith("&cid=C0123456789")


def test_cli_errors_exit_two_with_the_script_name() -> None:
    result = run_cli("permalink", "--workspace", "acme", "--channel", "bad", "--ts", "1.2")
    assert result.returncode == 2
    assert result.stderr.startswith("slack_helpers.py:")


def test_cli_batch_item_missing_a_field_exits_two() -> None:
    result = run_cli(
        "permalink", "--workspace", "acme", "--batch", stdin='[{"channel": "C0123456789"}]'
    )
    assert result.returncode == 2
    assert "missing field" in result.stderr


def test_cli_batch_rejects_non_json() -> None:
    result = run_cli("permalink", "--workspace", "acme", "--batch", stdin="not json")
    assert result.returncode == 2
    assert "not JSON" in result.stderr
