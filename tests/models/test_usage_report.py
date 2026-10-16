"""Tests for usage_report.py on synthetic transcripts. No real transcript is ever read."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "plugins/models/skills/usage-report/scripts/usage_report.py"
)
SPEC = importlib.util.spec_from_file_location("usage_report", SCRIPT)
assert SPEC and SPEC.loader
ur = importlib.util.module_from_spec(SPEC)
sys.modules["usage_report"] = ur
SPEC.loader.exec_module(ur)

NOW = datetime.now(UTC)


def assistant(
    msg_id: str,
    model: str,
    *,
    inp: int = 0,
    out: int = 0,
    read: int = 0,
    write: int = 0,
    write_1h: int = 0,
    tools: tuple[str, ...] = (),
    age: timedelta = timedelta(hours=1),
) -> dict[str, Any]:
    """One transcript line shaped like what Claude Code writes for an assistant response."""
    usage: dict[str, Any] = {
        "input_tokens": inp,
        "output_tokens": out,
        "cache_read_input_tokens": read,
        "cache_creation_input_tokens": write + write_1h,
        "cache_creation": {
            "ephemeral_5m_input_tokens": write,
            "ephemeral_1h_input_tokens": write_1h,
        },
    }
    return {
        "type": "assistant",
        "uuid": f"u-{msg_id}-{out}",
        "timestamp": (NOW - age).isoformat().replace("+00:00", "Z"),
        "message": {
            "id": msg_id,
            "model": model,
            "usage": usage,
            "content": [
                {"type": "tool_use", "id": f"t-{msg_id}-{i}", "name": name}
                for i, name in enumerate(tools)
            ],
        },
    }


def write_jsonl(path: Path, entries: list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(e) if not isinstance(e, str) else e for e in entries))


def add_subagent(
    root: Path,
    project: str,
    session: str,
    agent_id: str,
    entries: list[Any],
    *,
    agent_type: str = "explorer",
    description: str = "find the config files",
    model: str = "opus",
) -> None:
    base = root / project / session / "subagents"
    write_jsonl(base / f"{agent_id}.jsonl", entries)
    meta = {"agentType": agent_type, "description": description, "model": model, "spawnDepth": 1}
    (base / f"{agent_id}.meta.json").write_text(json.dumps(meta))


@pytest.fixture
def prices() -> dict[str, Any]:
    return ur.load_prices(ur.DEFAULT_PRICES)


def run_report(root: Path, prices: dict[str, Any], since: str = "all") -> dict[str, Any]:
    calls, stats = ur.load_calls(root, ur.parse_since(since))
    return ur.build_report(calls, stats, prices, top=10, mech_output_max=ur.MECH_OUTPUT_MAX)


# --- cost math -------------------------------------------------------------------------------


def test_cost_matches_hand_calculation(tmp_path: Path, prices: dict[str, Any]) -> None:
    # claude-sonnet-5-5: input 2, 5m write 2.5, 1h write 4, cache read 0.1, output 10 per MTok.
    line = assistant(
        "m1",
        "claude-sonnet-5-5",
        inp=1_000_000,
        out=1_000_000,
        read=1_000_000,
        write=1_000_000,
        write_1h=1_000_000,
    )
    write_jsonl(tmp_path / "proj" / "s1.jsonl", [line])
    report = run_report(tmp_path, prices)
    assert report["totals"]["cost_usd"] == pytest.approx(2 + 10 + 0.1 + 2.5 + 4)
    assert report["totals"]["calls"] == 1


def test_streamed_lines_of_one_response_count_once(tmp_path: Path, prices: dict[str, Any]) -> None:
    first = assistant("m1", "claude-sonnet-5-5", inp=10, out=5, tools=("Read",))
    last = assistant("m1", "claude-sonnet-5-5", inp=10, out=900, tools=("Grep",))
    write_jsonl(tmp_path / "proj" / "s1.jsonl", [first, last])
    report = run_report(tmp_path, prices)
    assert report["totals"]["calls"] == 1
    assert report["totals"]["output"] == 900


def test_resumed_history_in_a_second_file_is_not_double_counted(
    tmp_path: Path, prices: dict[str, Any]
) -> None:
    line = assistant("m1", "claude-sonnet-5-5", out=100)
    write_jsonl(tmp_path / "proj" / "a.jsonl", [line])
    write_jsonl(tmp_path / "proj" / "b.jsonl", [line])
    assert run_report(tmp_path, prices)["totals"]["calls"] == 1


def test_haiku_long_prompt_uses_the_higher_rate(prices: dict[str, Any]) -> None:
    price = ur.find_price("claude-haiku-5-5", prices)
    short = {
        "input": 100_000,
        "output": 0,
        "cache_read": 0,
        "cache_write_5m": 0,
        "cache_write_1h": 0,
    }
    long = {**short, "input": 100_001}
    assert ur.request_cost(short, price) == pytest.approx(100_000 * 0.1 / 1e6)
    assert ur.request_cost(long, price) == pytest.approx(100_001 * 0.5 / 1e6)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("us.anthropic.claude-opus-5-5-v1:0", "claude-opus-5-5"),
        ("anthropic.claude-sonnet-5-5", "claude-sonnet-5-5"),
        ("claude-haiku-4-5@20251001", "claude-haiku-4-5"),
        ("claude-sonnet-5-5", "claude-sonnet-5-5"),
    ],
)
def test_partner_ids_resolve_to_the_right_price_row(
    raw: str, expected: str, prices: dict[str, Any]
) -> None:
    assert ur.find_price(raw, prices)["match"] == expected


def test_longest_prefix_wins(prices: dict[str, Any]) -> None:
    assert ur.find_price("claude-sonnet-5-5", prices)["cache_read"] == 0.1
    assert ur.find_price("claude-sonnet-5", prices)["cache_read"] == 0.2


def test_unknown_model_costs_zero_and_warns(tmp_path: Path, prices: dict[str, Any]) -> None:
    write_jsonl(tmp_path / "p" / "s.jsonl", [assistant("m1", "claude-future-9", out=1000)])
    report = run_report(tmp_path, prices)
    assert report["totals"]["cost_usd"] == 0
    assert any("claude-future-9" in w for w in report["warnings"])
    assert report["by_model"][0]["tier"] == "unpriced"


def test_synthetic_model_is_ignored(tmp_path: Path, prices: dict[str, Any]) -> None:
    write_jsonl(tmp_path / "p" / "s.jsonl", [assistant("m1", "<synthetic>", out=50)])
    assert run_report(tmp_path, prices)["totals"]["calls"] == 0


# --- windows and bad input -------------------------------------------------------------------


def test_since_window_excludes_old_responses(tmp_path: Path, prices: dict[str, Any]) -> None:
    old = assistant("old", "claude-sonnet-5-5", out=1, age=timedelta(days=30))
    new = assistant("new", "claude-sonnet-5-5", out=2, age=timedelta(hours=2))
    write_jsonl(tmp_path / "p" / "s.jsonl", [old, new])
    assert run_report(tmp_path, prices, since="7d")["totals"]["calls"] == 1
    assert run_report(tmp_path, prices, since="all")["totals"]["calls"] == 2


def test_malformed_lines_are_skipped_and_reported(tmp_path: Path, prices: dict[str, Any]) -> None:
    good = assistant("m1", "claude-sonnet-5-5", out=10)
    write_jsonl(tmp_path / "p" / "s.jsonl", ["{not json", good, '"a string"', {"type": "user"}])
    report = run_report(tmp_path, prices)
    assert report["totals"]["calls"] == 1
    assert any("unreadable" in w for w in report["warnings"])


def test_stale_price_table_warns(tmp_path: Path, prices: dict[str, Any]) -> None:
    old = {**prices, "as_of": (NOW - timedelta(days=ur.STALE_PRICE_DAYS + 5)).date().isoformat()}
    write_jsonl(tmp_path / "p" / "s.jsonl", [assistant("m1", "claude-sonnet-5-5", out=1)])
    assert any("days old" in w for w in run_report(tmp_path, old)["warnings"])


def test_bad_since_value_names_the_fix() -> None:
    with pytest.raises(ur.UsageError, match="7d, 24h, all"):
        ur.parse_since("last week")


def test_missing_directory_exits_2_with_a_fix(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert ur.main(["--dir", str(tmp_path / "nope")]) == 2
    assert "pass --dir" in capsys.readouterr().err


def test_bad_price_file_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bad = tmp_path / "prices.json"
    bad.write_text("{")
    (tmp_path / "t").mkdir()
    assert ur.main(["--dir", str(tmp_path / "t"), "--prices", str(bad)]) == 2
    assert "not valid JSON" in capsys.readouterr().err


# --- subagents and the top-tier flag ---------------------------------------------------------


def test_subagent_cost_is_attributed_by_agent_type(tmp_path: Path, prices: dict[str, Any]) -> None:
    write_jsonl(tmp_path / "p" / "s1.jsonl", [assistant("main1", "claude-sonnet-5-5", out=10)])
    add_subagent(
        tmp_path,
        "p",
        "s1",
        "agent-a1",
        [assistant("sub1", "claude-sonnet-5-5", out=20)],
        agent_type="reviewer",
    )
    report = run_report(tmp_path, prices)
    types = {row["agent_type"]: row["calls"] for row in report["by_agent"]}
    assert types == {"main": 1, "reviewer": 1}


def test_top_tier_read_only_subagent_is_flagged(tmp_path: Path, prices: dict[str, Any]) -> None:
    add_subagent(
        tmp_path,
        "p",
        "s1",
        "agent-a1",
        [assistant("sub1", "claude-opus-5-5", out=400, read=50_000, tools=("Grep", "Read"))],
    )
    candidates = run_report(tmp_path, prices)["top_tier_candidates"]
    assert len(candidates) == 1
    found = candidates[0]
    assert found["model"] == "claude-opus-5-5"
    assert found["read_only"] is True
    assert found["cost_usd_at_mid"] < found["cost_usd"]
    assert found["cost_usd_at_small"] < found["cost_usd_at_mid"]
    assert any("search, list or summarize" in r for r in found["reasons"])


def test_subagent_that_edits_is_not_flagged(tmp_path: Path, prices: dict[str, Any]) -> None:
    add_subagent(
        tmp_path, "p", "s1", "a1", [assistant("s1", "claude-opus-5-5", out=300, tools=("Edit",))]
    )
    assert run_report(tmp_path, prices)["top_tier_candidates"] == []


def test_subagent_that_spawns_is_not_flagged(tmp_path: Path, prices: dict[str, Any]) -> None:
    add_subagent(
        tmp_path, "p", "s1", "a1", [assistant("s1", "claude-opus-5-5", out=300, tools=("Agent",))]
    )
    assert run_report(tmp_path, prices)["top_tier_candidates"] == []


def test_long_output_subagent_is_not_flagged(tmp_path: Path, prices: dict[str, Any]) -> None:
    big = assistant("s1", "claude-opus-5-5", out=ur.MECH_OUTPUT_MAX + 1, tools=("Read",))
    add_subagent(tmp_path, "p", "s1", "a1", [big])
    assert run_report(tmp_path, prices)["top_tier_candidates"] == []


def test_mid_tier_subagent_is_not_flagged(tmp_path: Path, prices: dict[str, Any]) -> None:
    add_subagent(
        tmp_path, "p", "s1", "a1", [assistant("s1", "claude-sonnet-5-5", out=10, tools=("Read",))]
    )
    assert run_report(tmp_path, prices)["top_tier_candidates"] == []


def test_judgment_wording_and_bash_are_marked_not_hidden(
    tmp_path: Path, prices: dict[str, Any]
) -> None:
    add_subagent(
        tmp_path,
        "p",
        "s1",
        "a1",
        [assistant("s1", "claude-opus-5-5", out=100, tools=("Read", "Bash"))],
        agent_type="security-reviewer",
        description="review the auth design",
    )
    found = run_report(tmp_path, prices)["top_tier_candidates"][0]
    assert found["judgment_hint"] is True
    assert found["ran_bash"] is True
    assert found["read_only"] is False


def test_orphaned_transcripts_are_not_read(tmp_path: Path, prices: dict[str, Any]) -> None:
    line = assistant("m1", "claude-sonnet-5-5", out=10)
    write_jsonl(tmp_path / "p" / "s1.orphaned-20261001-ab.jsonl", [line])
    assert run_report(tmp_path, prices)["totals"]["calls"] == 0


# --- output ----------------------------------------------------------------------------------


def test_text_report_names_every_section(tmp_path: Path, prices: dict[str, Any]) -> None:
    add_subagent(
        tmp_path, "p", "s1", "a1", [assistant("s1", "claude-opus-5-5", out=50, tools=("Read",))]
    )
    text = ur.render_text(run_report(tmp_path, prices), "all")
    for heading in ("By model", "By subagent type", "By project", "By session", "look mechanical"):
        assert heading in text
    assert "not a bill" in text


def test_json_output_round_trips(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_jsonl(tmp_path / "p" / "s.jsonl", [assistant("m1", "claude-sonnet-5-5", out=10)])
    assert ur.main(["--dir", str(tmp_path), "--since", "all", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["totals"]["calls"] == 1
    assert data["price_table"]["as_of"]


def test_empty_directory_is_a_valid_empty_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert ur.main(["--dir", str(tmp_path)]) == 0
    assert "Total: 0 responses" in capsys.readouterr().out
