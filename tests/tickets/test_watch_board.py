"""Tests for scripts/watch_board.py, driven by tracker responses saved in fixtures/watch_board.

The GitLab fixtures were captured read-only from a live GitLab board by running the watcher
with `--once` (plus REST reads of a merged, a closed and a missing merge request, and of a
request with a rejected token), then cut down to the fields the watcher reads. The values the
scenarios turn on (numbers, titles, draft, labels, merge status, author) were set per scenario,
and paths, names and the host replaced with placeholders."""

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
LANE_LABELS, LANE_STATUS = watch.registry.LaneMode.LABELS, watch.registry.LaneMode.STATUS


class RecordedCli:
    """Answers each tracker CLI call with a saved response, chosen by a fragment of the call."""

    def __init__(self, responses: dict[str, str | Exception]) -> None:
        self.responses = dict(responses)  # a test's changes stay in its own copy
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


def config(tracker: str, lane_mode: str = LANE_LABELS, ready: str = "Ready") -> object:
    if tracker == "github":
        board = watch.registry.GitHubBoard(owner="acme", number="1")
        return watch.Config("github.com", board, ready, None, "blocked", ("acme/shop-app",))
    board = watch.registry.GitLabBoard(
        scope="project", path="group/project", board="4", lanes=lane_mode
    )
    lane = "status::ready" if lane_mode == LANE_LABELS else ready
    return watch.Config("gitlab.example.com", board, lane, lane_mode, "blocked", ("group/project",))


def github_memory(data_dir: Path) -> Path:
    """The memory file of the board in the `filled_registry` fixture."""
    return watch.memory_path(data_dir, config("github").board)


def tracker_error(text: str, path: str = "user") -> object:
    """A failed CLI call as run_cli reports it: the call's first words, then the CLI's error."""
    return watch.TrackerError(f"'glab api --hostname gitlab.example.com {path}' exited 1: {text}")


# Per tracker: (config, the answers on tick 1, the answers once review 8 has merged).
SIGNED_IN = {"auth status": ""}
GITHUB_USER = {"github.com user": fixture("github_user.json")}
GITHUB_TICK_1 = {**SIGNED_IN, **GITHUB_USER, "graphql": fixture("github_tick1.json")}
GITLAB_USER = {"gitlab.example.com user": fixture("gitlab_user.json")}
GITLAB_LABEL_READY = {"/issues?": fixture("gitlab_ready_issues.ndjson")}
GITLAB_STATUS_READY = {"graphql": fixture("gitlab_ready_work_items.json")}
GITLAB_MRS = "author_username=user"
GITLAB_TICK_1 = {GITLAB_MRS: fixture("gitlab_mrs_tick1.ndjson")}
GITLAB_TICK_2 = {
    GITLAB_MRS: fixture("gitlab_mrs_tick2.ndjson"),
    "merge_requests/8": fixture("gitlab_mr_8.json"),
}
CASES = {
    "github": (
        config("github"),
        GITHUB_TICK_1,
        {"graphql": fixture("github_tick2.json"), "pulls/8": fixture("github_pull_8.json")},
    ),
    "gitlab-labels": (
        config("gitlab", LANE_LABELS),
        {**SIGNED_IN, **GITLAB_USER, **GITLAB_LABEL_READY, **GITLAB_TICK_1},
        {**GITLAB_LABEL_READY, **GITLAB_TICK_2},
    ),
    "gitlab-status": (
        config("gitlab", LANE_STATUS),
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
    tracker = watch.TRACKERS[type(cfg.board)](cfg, cli)
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
    cli = RecordedCli(GITHUB_TICK_1)
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


def gitlab_tracker(responses: dict[str, object]) -> object:
    cli = RecordedCli({**SIGNED_IN, **GITLAB_USER, **GITLAB_STATUS_READY, **responses})
    tracker = watch.GitLab(config("gitlab", LANE_STATUS), cli)
    tracker.sign_in()
    return tracker


def test_a_running_watcher_retries_a_failed_tick_and_stops_on_a_401(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    tracker = gitlab_tracker({GITLAB_MRS: watch.TrackerError("glab: connection reset by peer")})
    # Each sleep between ticks moves the tracker on: a good tick, then a rejected login.
    stages = iter([GITLAB_TICK_1, {GITLAB_MRS: tracker_error(fixture("gitlab_error_401.txt"))}])

    def sleep(_: float) -> None:
        tracker.run.responses.update(next(stages))

    with pytest.raises(watch.WatchError) as stopped:
        watch.watch(tracker, tmp_path / "memory.json", 60, False, sleep)
    assert stopped.value.code == watch.EXIT_AUTH
    assert "glab auth login --hostname gitlab.example.com" in str(stopped.value)
    out = capsys.readouterr()
    assert "the tick failed" in out.err and "connection reset" in out.err
    assert sorted(line.split(" ", 1)[0] for line in out.out.splitlines()) == [
        Event.CONFLICT, Event.NEW_READY, Event.QUEUE_READY
    ]  # fmt: skip


def test_once_exits_1_on_a_failed_tick_and_saves_nothing(
    filled_registry: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    failure = watch.TrackerError("'gh api --hostname github.com graphql' exited 1: HTTP 502")
    cli = RecordedCli({**SIGNED_IN, **GITHUB_USER, "graphql": failure})

    code = watch.main(["--data-dir", str(filled_registry), "--once"], run=cli)
    assert code == watch.EXIT_TICK_FAILED
    out = capsys.readouterr()
    assert out.out == "" and "HTTP 502" in out.err
    assert not github_memory(filled_registry).exists()


@pytest.mark.parametrize("bad", ["memory", "interval"])
def test_bad_input_exits_2(filled_registry: Path, bad: str) -> None:
    args = ["--data-dir", str(filled_registry), "--once"]
    if bad == "memory":
        path = github_memory(filled_registry)
        path.parent.mkdir()
        path.write_text("{not json", encoding="utf-8")
    else:
        args += ["--interval", "5"]
    cli = RecordedCli(GITHUB_TICK_1)
    assert watch.main(args, run=cli) == watch.EXIT_BAD_INPUT


@pytest.mark.parametrize(
    "answer", [fixture("gitlab_mr_8_closed.json"), tracker_error(fixture("gitlab_error_404.txt"))],
    ids=["closed", "deleted"],
)  # fmt: skip
def test_a_review_closed_or_deleted_fires_nothing(answer: object) -> None:
    tracker = gitlab_tracker(GITLAB_TICK_1)
    _, memory = watch.tick(tracker, watch.Memory.empty())

    tracker.run.responses.update({**GITLAB_TICK_2, "merge_requests/8": answer})
    events, memory = watch.tick(tracker, memory)
    assert events == []
    assert "group/project#8" not in memory.open_reviews


@pytest.mark.parametrize("number", [401, 404])
def test_a_failed_read_of_review_401_or_404_is_retried(tmp_path: Path, number: int) -> None:
    """The error quotes the API path, which ends in the review number: a server error on review
    401 is not a rejected login, and one on review 404 is not a deleted review."""
    item = watch.Item("group/project", number, "A review", "https://x", "user")
    path = tmp_path / "memory.json"
    watch.save(path, watch.Memory(watch.Memory.empty().active, {item.key: item}).to_json())
    api_path = f"projects/group%2Fproject/merge_requests/{number}"
    tracker = gitlab_tracker(
        {**GITLAB_TICK_2, f"merge_requests/{number}": tracker_error("HTTP 502", api_path)}
    )

    assert watch.watch(tracker, path, 60, True, lambda _: None) == watch.EXIT_TICK_FAILED
    assert item.key in watch.Memory.load(path).open_reviews


def test_an_open_review_missing_from_the_list_keeps_its_events() -> None:
    tracker = gitlab_tracker(GITLAB_TICK_1)
    _, memory = watch.tick(tracker, watch.Memory.empty())

    still_open = json.dumps({"iid": 8, "state": "opened"})
    tracker.run.responses.update({**GITLAB_TICK_2, "merge_requests/8": still_open})
    events, memory = watch.tick(tracker, memory)
    assert events == []
    assert "group/project#8" in memory.active[Event.QUEUE_READY]
    # Back in the list and still mergeable: QUEUE_READY does not fire a second time.
    tracker.run.responses.update(GITLAB_TICK_1)
    assert watch.tick(tracker, memory)[0] == []


def test_a_list_longer_than_a_page_is_reported(capsys: pytest.CaptureFixture[str]) -> None:
    lane = json.loads(fixture("gitlab_ready_work_items.json"))
    lane["data"]["namespace"]["workItems"]["pageInfo"]["hasNextPage"] = True
    tracker = gitlab_tracker({**GITLAB_TICK_1, "graphql": json.dumps(lane)})

    watch.tick(tracker, watch.Memory.empty())
    assert "the Ready lane has more than 100" in capsys.readouterr().err


def test_a_second_watcher_on_the_same_board_is_refused(
    filled_registry: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli = RecordedCli(GITHUB_TICK_1)
    path = github_memory(filled_registry)

    with watch.locked(path):  # the first watcher, still running
        code = watch.main(["--data-dir", str(filled_registry), "--once"], run=cli)
    assert code == watch.EXIT_ALREADY_WATCHING
    out = capsys.readouterr()
    assert out.out == "" and "another watcher already watches board acme/1" in out.err
    assert not any("graphql" in call for call in cli.calls)


@pytest.mark.parametrize(
    ("lane", "expected"),
    [("Ready", 'status:"Ready"'), ('Ready "now"', "status:'Ready \"now\"'")],
)
def test_the_github_lane_filter_quotes_the_lane(lane: str, expected: str) -> None:
    cli = RecordedCli(GITHUB_TICK_1)
    tracker = watch.GitHub(config("github", ready=lane), cli)
    tracker.sign_in()

    watch.tick(tracker, watch.Memory.empty())
    assert f"filter=is:issue is:open {expected}" in cli.calls[-1]


def test_a_github_lane_with_both_quotes_is_refused() -> None:
    cli = RecordedCli({**SIGNED_IN, **GITHUB_USER})
    tracker = watch.GitHub(config("github", ready='It\'s "done"'), cli)
    tracker.sign_in()

    with pytest.raises(watch.WatchError) as refused:
        watch.tick(tracker, watch.Memory.empty())
    assert refused.value.code == watch.EXIT_BAD_INPUT
    assert not any("graphql" in call for call in cli.calls)


def test_registry_bad_input_passes_through_as_exit_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """registry.py exits 2 when the plugin's example file is missing; that is not exit 3."""
    monkeypatch.setattr(watch.registry, "EXAMPLE", tmp_path / "missing.md")
    code = watch.main(["--data-dir", str(tmp_path / "data")], run=RecordedCli({}))
    assert code == watch.EXIT_BAD_INPUT
    assert "reinstall the plugin" in capsys.readouterr().err
