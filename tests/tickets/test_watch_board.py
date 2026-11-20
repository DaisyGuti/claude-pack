"""Tests for scripts/watch_board.py, driven by tracker responses saved in fixtures/watch_board."""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType

import pytest

PLUGIN = Path(__file__).resolve().parents[2] / "plugins" / "tickets"
SCRIPTS = PLUGIN / "scripts"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "watch_board"


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


watch = load_script("watch_board")
Event = watch.Event


class RecordedCli:
    """Answers each tracker CLI call with a saved response, chosen by a fragment of the call."""

    def __init__(self, responses: dict[str, str | Exception]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def __call__(self, argv: Sequence[str]) -> str:
        call = " ".join(argv)
        self.calls.append(call)
        for fragment, answer in self.responses.items():
            if fragment in call:
                if isinstance(answer, Exception):
                    raise answer
                return answer
        raise AssertionError(f"no saved response for: {call}")


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def config(tracker: str, lane_mode: str | None = None) -> object:
    board = (
        {"owner": "acme", "number": "1"}
        if tracker == "github"
        else {"scope": "project", "path": "acme/shop-app", "board": "4"}
    )
    ready = {"github": "Ready", "labels": "status::ready", "status": "Ready"}[lane_mode or tracker]
    host = "github.com" if tracker == "github" else "gitlab.example.com"
    blocked = "blocked" if tracker == "github" else "status::blocked"
    return watch.Config(tracker, host, board, ready, lane_mode, blocked, ("acme/shop-app",))


# Per tracker: (config, the answers on tick 1, the answers once review 8 has merged).
SIGNED_IN = {"auth status": ""}
GITHUB_USER = {"github.com user": fixture("github_user.json")}
GITLAB_USER = {"gitlab.example.com user": fixture("gitlab_user.json")}
GITLAB_LABEL_READY = {"/issues?": fixture("gitlab_ready_issues.ndjson")}
GITLAB_STATUS_READY = {"graphql": fixture("gitlab_ready_work_items.json")}
GITLAB_TICK_1 = {"author_username=acme-dev": fixture("gitlab_mrs_tick1.ndjson")}
GITLAB_TICK_2 = {
    "author_username=acme-dev": fixture("gitlab_mrs_tick2.ndjson"),
    "merge_requests/8": fixture("gitlab_mr_8.json"),
}
CASES = {
    "github": (
        config("github"),
        {**SIGNED_IN, **GITHUB_USER, "graphql": fixture("github_tick1.json")},
        {"graphql": fixture("github_tick2.json"), "pulls/8": fixture("github_pull_8.json")},
    ),
    "gitlab-labels": (
        config("gitlab", "labels"),
        {**SIGNED_IN, **GITLAB_USER, **GITLAB_LABEL_READY, **GITLAB_TICK_1},
        {**GITLAB_LABEL_READY, **GITLAB_TICK_2},
    ),
    "gitlab-status": (
        config("gitlab", "status"),
        {**SIGNED_IN, **GITLAB_USER, **GITLAB_STATUS_READY, **GITLAB_TICK_1},
        {**GITLAB_STATUS_READY, **GITLAB_TICK_2},
    ),
}


def events_of(lines: list[tuple[object, object]]) -> list[tuple[str, int]]:
    return sorted((str(event), item.number) for event, item in lines)


@pytest.mark.parametrize("case", CASES, ids=list(CASES))
def test_each_event_fires_once(case: str) -> None:
    cfg, first, merged = CASES[case]
    cli = RecordedCli(first)
    tracker = watch.TRACKERS[cfg.tracker](cfg, cli)
    tracker.sign_in()

    events, memory = watch.tick(tracker, watch.Memory.empty())
    # Ticket 12 is Ready (ticket 3 is in a repo outside the registry), review 7 conflicts and
    # review 8 can be queued. Review 9 is pending; 10 is someone else's, 11 a draft and 13
    # blocked, so none of them is ready to queue whatever its merge state says.
    assert events_of(events) == [("CONFLICT", 7), ("NEW_READY", 12), ("QUEUE_READY", 8)]
    repeat, memory = watch.tick(tracker, memory)
    assert repeat == []

    cli.responses = merged
    events, memory = watch.tick(tracker, memory)
    assert events_of(events) == [("MERGED", 8)]
    assert watch.tick(tracker, memory)[0] == []
    # Read-only: every call is an auth check, a GraphQL query or a REST read.
    assert not any("mutation" in call or " -X " in call or " -f body" in call for call in cli.calls)


def test_nothing_changed_prints_nothing_across_runs(
    filled_registry: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli = RecordedCli({**SIGNED_IN, **GITHUB_USER, "graphql": fixture("github_tick1.json")})
    args = ["--data-dir", str(filled_registry), "--once"]

    assert watch.main(args, run=cli) == 0
    lines = capsys.readouterr().out.splitlines()
    assert sorted(line.split(" ", 1)[0] for line in lines) == [
        Event.CONFLICT, Event.NEW_READY, Event.QUEUE_READY
    ]  # fmt: skip
    name, payload = lines[0].split(" ", 1)
    assert set(json.loads(payload)) == {"repo", "number", "title", "url", "author"}

    # A second run reads the memory the first one saved, so the same board prints nothing.
    assert watch.main(args, run=cli) == 0
    assert capsys.readouterr().out == ""


def test_refuses_when_not_signed_in(
    filled_registry: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli = RecordedCli({"auth status": watch.TrackerError("gh auth status exited 1")})

    assert watch.main(["--data-dir", str(filled_registry)], run=cli) == watch.EXIT_AUTH
    out = capsys.readouterr()
    assert out.out == ""
    assert "gh auth login --hostname github.com" in out.err
    assert cli.calls == ["gh auth status --hostname github.com"]


def test_a_recomputed_merge_state_does_not_fire_again() -> None:
    """GitHub reads UNKNOWN while it recomputes a review after its target branch moved."""
    ready = json.loads(fixture("github_tick1.json"))
    recomputing = json.loads(fixture("github_tick1.json"))
    for pr in recomputing["data"]["r0"]["pullRequests"]["nodes"]:
        pr["mergeable"] = pr["mergeStateStatus"] = "UNKNOWN"
    cli = RecordedCli({**SIGNED_IN, **GITHUB_USER, "graphql": json.dumps(ready)})
    tracker = watch.GitHub(config("github"), cli)
    tracker.sign_in()
    _, memory = watch.tick(tracker, watch.Memory.empty())

    cli.responses["graphql"] = json.dumps(recomputing)
    events, memory = watch.tick(tracker, memory)
    assert events == []
    cli.responses["graphql"] = json.dumps(ready)
    assert watch.tick(tracker, memory)[0] == []
