#!/usr/bin/env python3
"""Watch the board and print one line per new event: the one poller `work-tickets` acts on.

Every tick reads the registry's Ready lane and the open reviews of each registry repo, then
prints a line for each event it has not printed before. It only reads the tracker; nothing
here moves a card, labels an issue or merges a review. The event contract (names, fields and
when each fires) is `references/board-watcher.md`.

What it has printed is kept in `<data dir>/state/board-watcher-<board>.json`, so a restart
does not print the same events again.

Usage:
    watch_board.py --data-dir DIR [--interval SECONDS] [--once]

Exit codes: 0 stopped (after one tick with --once, or by Ctrl-C), 1 the tick failed (--once
only; a long-running watcher reports the failure and tries again next tick), 2 bad input or an
unreadable memory file, 3 the registry is missing or incomplete, 4 the tracker CLI is not
signed in.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import quote

if sys.version_info < (3, 11):  # noqa: UP036  (a clear message on an older python3)
    sys.exit("watch_board.py needs Python 3.11 or newer; install it and run this again")

import registry  # noqa: E402  (after the version check, like the other scripts' imports)
from ticket_state import safe_name, save  # noqa: E402

EXIT_TICK_FAILED = 1
EXIT_BAD_INPUT = 2
EXIT_REGISTRY = 3
EXIT_AUTH = 4
DEFAULT_INTERVAL = 60
# Every worker and session on the machine shares the tracker's rate limit.
MIN_INTERVAL = 10
MEMORY_SCHEMA = 1
# SIMPLIFIED: one page per list (100 Ready tickets, 100 open reviews per repo); a longer list
# is reported on stderr and the rest is not watched. The full version pages through the list.
PAGE = 100

# The tracker values that decide a review's readiness. GitHub: PullRequest.mergeable and
# mergeStateStatus (CLEAN: checks and required reviews pass; HAS_HOOKS: the same, plus hooks).
GITHUB_CONFLICTING = "CONFLICTING"
GITHUB_QUEUE_READY = frozenset({"CLEAN", "HAS_HOOKS"})
# GitLab: a merge request's detailed_merge_status.
GITLAB_CONFLICT = "conflict"
GITLAB_QUEUE_READY = "mergeable"
# `locked` is the moment a merge completes; the merge request is still open.
GITLAB_OPEN_STATES = frozenset({"opened", "locked"})
GITLAB_LANE_STATUS = "status"


class Event(StrEnum):
    """The event names a line starts with. The contract is references/board-watcher.md."""

    NEW_READY = "NEW_READY"
    CONFLICT = "CONFLICT"
    QUEUE_READY = "QUEUE_READY"
    MERGED = "MERGED"


class Readiness(StrEnum):
    """Where an open review stands for the merge queue."""

    PENDING = "pending"  # a draft, checks running or failing, approvals missing, not computed
    CONFLICT = "conflict"
    QUEUE_READY = "queue_ready"


class ReviewState(StrEnum):
    OPEN = "open"
    MERGED = "merged"
    CLOSED = "closed"


READINESS_EVENT = {Readiness.CONFLICT: Event.CONFLICT, Readiness.QUEUE_READY: Event.QUEUE_READY}
# The events that hold while a condition is true; MERGED happens once and holds nothing.
CONDITION_EVENTS = (Event.NEW_READY, Event.CONFLICT, Event.QUEUE_READY)


@dataclass(frozen=True)
class Item:
    """A ticket or a review: the fields every event line carries."""

    repo: str
    number: int
    title: str
    url: str

    @property
    def key(self) -> str:
        return f"{self.repo}#{self.number}"


@dataclass(frozen=True)
class Review:
    item: Item
    readiness: Readiness


@dataclass(frozen=True)
class Snapshot:
    """One tick's read of the tracker."""

    ready: tuple[Item, ...]
    reviews: tuple[Review, ...]


@dataclass(frozen=True)
class Memory:
    """What has been printed: the items each condition event holds now, and the open reviews
    (kept so a review that leaves the open list can be checked for a merge)."""

    active: dict[Event, frozenset[str]]
    open_reviews: dict[str, Item]

    @classmethod
    def empty(cls) -> Memory:
        return cls({event: frozenset() for event in CONDITION_EVENTS}, {})

    @classmethod
    def load(cls, path: Path) -> Memory:
        if not path.exists():
            return cls.empty()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if raw["schema_version"] != MEMORY_SCHEMA:
                raise ValueError(f"schema_version {raw['schema_version']!r}")
            return cls(
                {event: frozenset(raw["active"][event]) for event in CONDITION_EVENTS},
                {key: Item(**item) for key, item in raw["open_reviews"].items()},
            )
        except (ValueError, KeyError, TypeError) as err:
            raise WatchError(
                f"{path} is not a memory file this script reads ({err}); delete it to start "
                "fresh (the next tick then prints every current event once)",
                EXIT_BAD_INPUT,
            ) from err

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": MEMORY_SCHEMA,
            "active": {event.value: sorted(keys) for event, keys in self.active.items()},
            "open_reviews": {key: asdict(item) for key, item in self.open_reviews.items()},
        }


class WatchError(Exception):
    """A problem that stops the watcher; carries the exit code."""

    def __init__(self, message: str, code: int) -> None:
        super().__init__(message)
        self.code = code


class TrackerError(Exception):
    """A tracker CLI call failed or answered with something unexpected."""


Run = Callable[[Sequence[str]], str]


def run_cli(argv: Sequence[str]) -> str:
    """Run a tracker CLI command and return its stdout; a non-zero exit is a TrackerError."""
    proc = subprocess.run(list(argv), capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()
        raise TrackerError(f"'{' '.join(argv[:3])}' exited {proc.returncode}: {detail}")
    return proc.stdout


@dataclass(frozen=True)
class Config:
    """The registry facts the watcher reads."""

    tracker: str
    host: str
    board: dict[str, str]
    ready_lane: str
    lane_mode: str | None
    repos: tuple[str, ...]

    @classmethod
    def from_registry(cls, reg: dict[str, Any]) -> Config:
        return cls(
            tracker=reg["tracker"],
            host=reg["host"],
            board=reg["board"],
            ready_lane=reg["lanes"]["ready"],
            lane_mode=reg["lane_mode"],
            repos=tuple(repo["remote"] for repo in reg["repos"]),
        )


class Tracker:
    """What both trackers share: the CLI, the sign-in check and the board's memory key."""

    cli: str

    def __init__(self, config: Config, run: Run) -> None:
        self.config = config
        self.run = run

    @property
    def board_key(self) -> str:
        raise NotImplementedError

    def signed_in(self) -> bool:
        try:
            self.run([self.cli, "auth", "status", "--hostname", self.config.host])
        except TrackerError:
            return False
        return True

    def auth_message(self) -> str:
        host = self.config.host
        return (
            f"error: {self.cli} is not signed in to {host}, or its login was rejected. Run "
            f"'{self.cli} auth login --hostname {host}', then start the watcher again."
        )

    def snapshot(self) -> Snapshot:
        raise NotImplementedError

    def review_state(self, repo: str, number: int) -> ReviewState:
        raise NotImplementedError


def warn_truncated(what: str) -> None:
    print(f"watch_board.py: {what} has more than {PAGE}; only the first {PAGE} are watched",
          file=sys.stderr)  # fmt: skip


def parse_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as err:
        raise TrackerError(f"the tracker CLI printed something that is not JSON ({err})") from err


class GitHub(Tracker):
    """GitHub Projects (v2): one GraphQL query per tick reads the Ready lane and every repo's
    open pull requests; REST reads a pull request that left the open list."""

    cli = "gh"

    @property
    def board_key(self) -> str:
        return f"{self.config.board['owner']}/{self.config.board['number']}"

    def api(self, *args: str) -> Any:
        return parse_json(self.run([self.cli, "api", "--hostname", self.config.host, *args]))

    def snapshot(self) -> Snapshot:
        # Repo names travel as variables, never spliced into the query text.
        declarations = ["$owner: String!", "$number: Int!", "$filter: String!"]
        fields = [
            "-f", f"owner={self.config.board['owner']}",
            "-F", f"number={self.config.board['number']}",
            "-f", f'filter=is:issue is:open status:"{self.config.ready_lane}"',
        ]  # fmt: skip
        selections = []
        for index, remote in enumerate(self.config.repos):
            owner, name = remote.split("/", 1)
            declarations += [f"$o{index}: String!", f"$n{index}: String!"]
            selections.append(f"r{index}: repository(owner: $o{index}, name: $n{index}) {{...R}}")
            fields += ["-f", f"o{index}={owner}", "-f", f"n{index}={name}"]
        query = (
            f"query({', '.join(declarations)}) {{\n"
            "  owner: repositoryOwner(login: $owner) { ... on ProjectV2Owner {\n"
            f"    projectV2(number: $number) {{ items(first: {PAGE}, query: $filter) {{\n"
            "      pageInfo { hasNextPage }\n"
            "      nodes { content { ... on Issue {\n"
            "        number title url repository { nameWithOwner } } } } } } } }\n"
            f"  {' '.join(selections)}\n"
            "}\n"
            f"fragment R on Repository {{ nameWithOwner pullRequests(states: OPEN, first: {PAGE},\n"
            "  orderBy: {field: UPDATED_AT, direction: DESC}) {\n"
            "  pageInfo { hasNextPage }\n"
            "  nodes { number title url mergeable mergeStateStatus } } }\n"
        )
        data = self.api("graphql", "-f", f"query={query}", *fields)["data"]
        project = (data["owner"] or {}).get("projectV2")
        if project is None:
            raise TrackerError(f"board {self.board_key} was not found or this login cannot read it")
        if project["items"]["pageInfo"]["hasNextPage"]:
            warn_truncated(f"the {self.config.ready_lane} lane")
        ready = tuple(
            Item(c["repository"]["nameWithOwner"], c["number"], c["title"], c["url"])
            for node in project["items"]["nodes"]
            if (c := node["content"])  # empty for an item this login cannot see
        )
        reviews: list[Review] = []
        for index, remote in enumerate(self.config.repos):
            repo = data[f"r{index}"]
            if repo is None:
                raise TrackerError(f"repo {remote} was not found or this login cannot read it")
            pulls = repo["pullRequests"]
            if pulls["pageInfo"]["hasNextPage"]:
                warn_truncated(f"{remote}'s open pull request list")
            reviews += [
                Review(Item(remote, pr["number"], pr["title"], pr["url"]), self.readiness(pr))
                for pr in pulls["nodes"]
            ]
        return Snapshot(ready, tuple(reviews))

    @staticmethod
    def readiness(pr: dict[str, Any]) -> Readiness:
        if pr["mergeable"] == GITHUB_CONFLICTING:
            return Readiness.CONFLICT
        if pr["mergeStateStatus"] in GITHUB_QUEUE_READY:
            return Readiness.QUEUE_READY
        return Readiness.PENDING

    def review_state(self, repo: str, number: int) -> ReviewState:
        pull = self.api(f"repos/{repo}/pulls/{number}")
        if pull["merged"]:
            return ReviewState.MERGED
        return ReviewState(pull["state"])


class GitLab(Tracker):
    """GitLab issue boards, in label or Status lane mode (`references/trackers/gitlab.md`):
    REST for label lanes and merge requests, one GraphQL query for Status lanes."""

    cli = "glab"

    @property
    def board_key(self) -> str:
        return f"{self.config.board['path']}/{self.config.board['board']}"

    def api(self, *args: str) -> str:
        return self.run([self.cli, "api", "--hostname", self.config.host, *args])

    def ndjson(self, path: str) -> list[dict[str, Any]]:
        out = self.api("--paginate", "--output", "ndjson", path)
        return [parse_json(line) for line in out.splitlines() if line.strip()]

    def snapshot(self) -> Snapshot:
        reviews: list[Review] = []
        for remote in self.config.repos:
            mrs = self.ndjson(
                f"projects/{quote(remote, safe='')}/merge_requests?state=opened&per_page={PAGE}"
            )
            reviews += [
                Review(Item(remote, mr["iid"], mr["title"], mr["web_url"]), self.readiness(mr))
                for mr in mrs
            ]
        return Snapshot(self.ready(), tuple(reviews))

    def ready(self) -> tuple[Item, ...]:
        board = self.config.board
        if self.config.lane_mode == GITLAB_LANE_STATUS:
            return self.ready_by_status(board["path"])
        scope = f"{board['scope']}s"  # the registry's group or project
        issues = self.ndjson(
            f"{scope}/{quote(board['path'], safe='')}/issues?state=opened&per_page={PAGE}"
            f"&labels={quote(self.config.ready_lane, safe='')}"
        )
        return tuple(
            Item(issue["references"]["full"].rsplit("#", 1)[0], issue["iid"], issue["title"],
                 issue["web_url"])
            for issue in issues
        )  # fmt: skip

    def ready_by_status(self, path: str) -> tuple[Item, ...]:
        query = (
            "query($path: ID!, $lane: String) { namespace(fullPath: $path) {\n"
            "  workItems(state: opened, types: [ISSUE], includeDescendants: true,\n"
            f"            status: {{name: $lane}}, first: {PAGE}) {{\n"
            "    pageInfo { hasNextPage }\n"
            "    nodes { iid title webUrl namespace { fullPath } } } } }\n"
        )
        out = self.api(
            "graphql", "-f", f"path={path}", "-f", f"lane={self.config.ready_lane}",
            "-f", f"query={query}",
        )  # fmt: skip
        namespace = parse_json(out)["data"]["namespace"]
        if namespace is None:
            raise TrackerError(f"{path} was not found or this login cannot read it")
        items = namespace["workItems"]
        if items["pageInfo"]["hasNextPage"]:
            warn_truncated(f"the {self.config.ready_lane} lane")
        return tuple(
            Item(node["namespace"]["fullPath"], int(node["iid"]), node["title"], node["webUrl"])
            for node in items["nodes"]
        )

    @staticmethod
    def readiness(mr: dict[str, Any]) -> Readiness:
        if mr["has_conflicts"] or mr["detailed_merge_status"] == GITLAB_CONFLICT:
            return Readiness.CONFLICT
        if mr["detailed_merge_status"] == GITLAB_QUEUE_READY:
            return Readiness.QUEUE_READY
        return Readiness.PENDING

    def review_state(self, repo: str, number: int) -> ReviewState:
        mr = parse_json(self.api(f"projects/{quote(repo, safe='')}/merge_requests/{number}"))
        state = mr["state"]
        return ReviewState.OPEN if state in GITLAB_OPEN_STATES else ReviewState(state)


TRACKERS: dict[str, type[Tracker]] = {"github": GitHub, "gitlab": GitLab}


def tick(tracker: Tracker, memory: Memory) -> tuple[list[tuple[Event, Item]], Memory]:
    """Read the tracker once; return the events not printed before and the memory after them.

    The memory is returned, not changed in place, so a tick that fails part way prints nothing
    and forgets nothing."""
    snapshot = tracker.snapshot()
    holding: dict[Event, dict[str, Item]] = {event: {} for event in CONDITION_EVENTS}
    holding[Event.NEW_READY] = {item.key: item for item in snapshot.ready}
    for review in snapshot.reviews:
        if event := READINESS_EVENT.get(review.readiness):
            holding[event][review.item.key] = review.item
    events = [
        (event, item)
        for event, items in holding.items()
        for key, item in items.items()
        if key not in memory.active[event]
    ]
    open_now = {review.item.key: review.item for review in snapshot.reviews}
    events += [
        (Event.MERGED, item)
        for key, item in memory.open_reviews.items()
        if key not in open_now
        and tracker.review_state(item.repo, item.number) is ReviewState.MERGED
    ]
    return events, Memory({event: frozenset(items) for event, items in holding.items()}, open_now)


def event_line(event: Event, item: Item) -> str:
    return f"{event} {json.dumps(asdict(item), ensure_ascii=False)}"


def memory_path(data_dir: Path, tracker: Tracker) -> Path:
    return data_dir / "state" / f"board-watcher-{safe_name(tracker.board_key)}.json"


def main(argv: list[str], run: Run = run_cli, sleep: Callable[[float], None] = time.sleep) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--data-dir", required=True, type=Path, help="the plugin's data folder")
    parser.add_argument(
        "--interval", type=int, default=DEFAULT_INTERVAL,
        help=f"seconds between ticks (default {DEFAULT_INTERVAL}, at least {MIN_INTERVAL})",
    )  # fmt: skip
    parser.add_argument("--once", action="store_true", help="run one tick, then exit")
    args = parser.parse_args(argv)
    if args.interval < MIN_INTERVAL:
        print(f"error: --interval must be at least {MIN_INTERVAL} seconds", file=sys.stderr)
        return EXIT_BAD_INPUT
    data_dir = args.data_dir.expanduser()

    code, payload = registry.ensure(data_dir)
    if code != 0:
        print(json.dumps(payload, indent=2), file=sys.stderr)
        return EXIT_REGISTRY
    config = Config.from_registry(
        registry.parse(registry.registry_path(data_dir).read_text(encoding="utf-8"))
    )
    tracker = TRACKERS[config.tracker](config, run)
    if not tracker.signed_in():
        print(tracker.auth_message(), file=sys.stderr)
        return EXIT_AUTH
    path = memory_path(data_dir, tracker)
    try:
        memory = Memory.load(path)
    except WatchError as err:
        print(f"error: {err}", file=sys.stderr)
        return err.code
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        while True:
            try:
                events, after = tick(tracker, memory)
            except TrackerError as err:
                if not tracker.signed_in():
                    print(tracker.auth_message(), file=sys.stderr)
                    return EXIT_AUTH
                print(f"watch_board.py: the tick failed: {err}", file=sys.stderr, flush=True)
                if args.once:
                    return EXIT_TICK_FAILED
            else:
                for event, item in events:
                    print(event_line(event, item), flush=True)
                # Printed before saved: a crash between the two prints those events again on
                # restart (at least once), never loses one.
                save(path, after.to_json())
                memory = after
            if args.once:
                return 0
            sleep(args.interval)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
