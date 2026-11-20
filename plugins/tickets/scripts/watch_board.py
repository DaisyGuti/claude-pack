#!/usr/bin/env python3
"""Watch the board and print one line per new event: the one poller `work-tickets` acts on.

Every tick reads the registry's Ready lane and the signed-in user's open reviews in each
registry repo, then prints a line for each event it has not printed before. It only reads the
tracker; nothing here moves a card, labels an issue or merges a review. The event contract
(names, fields and when each fires) is `references/board-watcher.md`.

What it has printed is kept in `<data dir>/state/board-watcher-<board>-<hash>.json`, so a restart
does not print the same events again.

Usage:
    watch_board.py --data-dir DIR [--interval SECONDS] [--once]

Exit codes: 0 stopped (after one tick with --once, or by Ctrl-C), 1 the tick failed (--once
only; a long-running watcher reports the failure and tries again next tick), 2 bad input, an
unreadable memory file or the plugin's registry example missing, 3 the registry is missing or
incomplete, 4 the tracker CLI is not signed in or its login was rejected, 5 another watcher
already watches this board from this data folder.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
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
from ticket_state import LockHeld, locked, safe_name, save  # noqa: E402

EXIT_TICK_FAILED = 1
EXIT_BAD_INPUT = 2
EXIT_REGISTRY = 3
EXIT_AUTH = 4
EXIT_ALREADY_WATCHING = 5
DEFAULT_INTERVAL = 60
# Every worker and session on the machine shares the tracker's rate limit.
MIN_INTERVAL = 10
MEMORY_SCHEMA = 1
# SIMPLIFIED: a GraphQL list reads one page (100 Ready tickets; 100 open pull requests per
# GitHub repo) and says so on stderr when there are more. The full version pages through it.
PAGE = 100
# How gh and glab report a rejected or missing login, and a missing object, in their errors
# (glab prints `glab: 401 Unauthorized (HTTP 401)` and `glab: 404 Not found (HTTP 404)`, gh
# `HTTP 401: Bad credentials`). Only the printed status counts: the error also quotes the API
# path, which ends in a review number that may be 401 or 404.
AUTH_FAILURE = re.compile(r"HTTP 401\b|Bad credentials|not been authenticated|not logged in")
NOT_FOUND = re.compile(r"HTTP 404\b")

# The tracker values that decide a review's merge state. GitHub: PullRequest.mergeable and
# mergeStateStatus (CLEAN: checks and required reviews pass; HAS_HOOKS: the same, plus hooks).
GITHUB_CONFLICTING = "CONFLICTING"
GITHUB_UNKNOWN = "UNKNOWN"
GITHUB_QUEUE_READY = frozenset({"CLEAN", "HAS_HOOKS"})
# GitLab: a merge request's detailed_merge_status.
GITLAB_CONFLICT = "conflict"
GITLAB_QUEUE_READY = "mergeable"
GITLAB_UNKNOWN = frozenset({"checking", "unchecked", "preparing", "approvals_syncing"})
# `locked` is the moment a merge completes; the merge request is still open.
GITLAB_OPEN_STATES = frozenset({"opened", "locked"})


class Event(StrEnum):
    """The event names a line starts with. The contract is references/board-watcher.md."""

    NEW_READY = "NEW_READY"
    CONFLICT = "CONFLICT"
    QUEUE_READY = "QUEUE_READY"
    MERGED = "MERGED"


class Readiness(StrEnum):
    """Where an open review stands for the merge queue."""

    PENDING = "pending"  # a draft, blocked, checks running or failing, approvals missing
    UNKNOWN = "unknown"  # the tracker is recomputing it (after the target branch moved)
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
    author: str | None  # None for an account the tracker no longer has

    @property
    def key(self) -> str:
        return f"{self.repo}#{self.number}"


@dataclass(frozen=True)
class Review:
    """An open review as the tracker reports it, before the watcher's own rules apply."""

    item: Item
    merge: Readiness
    draft: bool
    labels: frozenset[str]


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
        # argv[4] is the API path or `graphql`; the query text after it is too long to show.
        raise TrackerError(f"'{' '.join(argv[:5])}' exited {proc.returncode}: {detail}")
    return proc.stdout


def parse_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as err:
        raise TrackerError(f"the tracker CLI printed something that is not JSON ({err})") from err


def encode(path: str) -> str:
    """A group or project path as one URL segment (`a/b` -> `a%2Fb`)."""
    return quote(path, safe="")


def warn_truncated(what: str) -> None:
    print(f"watch_board.py: {what} has more than {PAGE}; only the first {PAGE} are watched",
          file=sys.stderr)  # fmt: skip


@dataclass(frozen=True)
class Config:
    """The registry facts the watcher reads."""

    host: str
    board: registry.Board
    ready_lane: str
    lane_mode: str | None
    blocked_label: str
    repos: tuple[str, ...]

    @classmethod
    def from_registry(cls, reg: dict[str, Any]) -> Config:
        return cls(
            host=reg["host"],
            board=reg["board"],
            ready_lane=reg["lanes"]["ready"],
            lane_mode=reg["lane_mode"],
            blocked_label=reg["labels"]["blocked"]["name"],
            repos=tuple(repo["remote"] for repo in reg["repos"]),
        )


class Tracker:
    """What both trackers share: the CLI, the sign-in, and the rules that decide which reviews
    and tickets the watcher reports. Each tracker reads its own snapshot and review state."""

    cli: str

    def __init__(self, config: Config, run: Run) -> None:
        self.config = config
        self.run = run
        self.login = ""

    def api(self, *args: str) -> str:
        return self.run([self.cli, "api", "--hostname", self.config.host, *args])

    def sign_in(self) -> None:
        """Confirm the CLI's login on the registry's host and remember the account name, whose
        reviews (opened by the user or by the workers, which use the same login) are watched."""
        try:
            self.run([self.cli, "auth", "status", "--hostname", self.config.host])
            self.login = self.read_login()
        except TrackerError as err:
            raise WatchError(self.auth_message(err), EXIT_AUTH) from err

    def auth_message(self, err: TrackerError) -> str:
        host = self.config.host
        return (
            f"error: {self.cli} is not signed in to {host}, or its login was rejected ({err}). "
            f"Run '{self.cli} auth login --hostname {host}', then start the watcher again."
        )

    def snapshot(self) -> Snapshot:
        """The Ready tickets in the registry's repos, and the signed-in user's open reviews."""
        raw = self.read_snapshot()
        repos = set(self.config.repos)
        mine = self.login.casefold()
        return Snapshot(
            tuple(item for item in raw.ready if item.repo in repos),
            tuple(r for r in raw.reviews if (r.item.author or "").casefold() == mine),
        )

    def readiness(self, review: Review) -> Readiness:
        """A draft or a review carrying the blocked label is never ready, whatever it reports."""
        if review.draft or self.config.blocked_label in review.labels:
            return Readiness.PENDING
        return review.merge

    def state_of(self, item: Item) -> ReviewState:
        """Whether a review that left the open list merged. One deleted since reads as closed."""
        try:
            return self.read_review_state(item.repo, item.number)
        except TrackerError as err:
            if NOT_FOUND.search(str(err)):
                return ReviewState.CLOSED
            raise

    def read_login(self) -> str:
        raise NotImplementedError

    def read_snapshot(self) -> Snapshot:
        raise NotImplementedError

    def read_review_state(self, repo: str, number: int) -> ReviewState:
        raise NotImplementedError


class GitHub(Tracker):
    """GitHub Projects (v2): one GraphQL query per tick reads the Ready lane and every repo's
    open pull requests; REST reads the login and a pull request that left the open list."""

    cli = "gh"

    def read_login(self) -> str:
        return str(parse_json(self.api("user"))["login"])

    def read_snapshot(self) -> Snapshot:
        # Repo names travel as variables, never spliced into the query text.
        aliases = [(f"r{index}", remote) for index, remote in enumerate(self.config.repos)]
        declarations = ["$owner: String!", "$number: Int!", "$filter: String!"]
        fields = [
            "-f", f"owner={self.config.board.owner}",
            "-F", f"number={self.config.board.number}",
            "-f", f"filter=is:issue is:open status:{filter_value(self.config.ready_lane)}",
        ]  # fmt: skip
        selections = []
        for alias, remote in aliases:
            owner, name = remote.split("/", 1)
            declarations += [f"${alias}o: String!", f"${alias}n: String!"]
            selections.append(f"{alias}: repository(owner: ${alias}o, name: ${alias}n) {{...R}}")
            fields += ["-f", f"{alias}o={owner}", "-f", f"{alias}n={name}"]
        query = (
            f"query({', '.join(declarations)}) {{\n"
            "  owner: repositoryOwner(login: $owner) { ... on ProjectV2Owner {\n"
            f"    projectV2(number: $number) {{ items(first: {PAGE}, query: $filter) {{\n"
            "      pageInfo { hasNextPage }\n"
            "      nodes { content { ... on Issue {\n"
            "        number title url author { login } repository { nameWithOwner } } } } } } } }\n"
            f"  {' '.join(selections)}\n"
            "}\n"
            f"fragment R on Repository {{ pullRequests(states: OPEN, first: {PAGE},\n"
            "  orderBy: {field: UPDATED_AT, direction: DESC}) {\n"
            "  pageInfo { hasNextPage }\n"
            "  nodes { number title url author { login } isDraft\n"
            "    labels(first: 50) { nodes { name } } mergeable mergeStateStatus } } }\n"
        )
        data = parse_json(self.api("graphql", "-f", f"query={query}", *fields))["data"]
        project = (data["owner"] or {}).get("projectV2")
        if project is None:
            raise TrackerError(
                f"board {self.config.board.key} was not found or this login cannot read it"
            )
        if project["items"]["pageInfo"]["hasNextPage"]:
            warn_truncated(f"the {self.config.ready_lane} lane")
        ready = tuple(
            Item(
                c["repository"]["nameWithOwner"],
                c["number"],
                c["title"],
                c["url"],
                github_author(c),
            )
            for node in project["items"]["nodes"]
            if (c := node["content"])  # empty for an item this login cannot see
        )
        reviews: list[Review] = []
        for alias, remote in aliases:
            if data[alias] is None:
                raise TrackerError(f"repo {remote} was not found or this login cannot read it")
            pulls = data[alias]["pullRequests"]
            if pulls["pageInfo"]["hasNextPage"]:
                warn_truncated(f"{remote}'s open pull request list")
            reviews += [
                Review(
                    Item(remote, pr["number"], pr["title"], pr["url"], github_author(pr)),
                    self.merge_state(pr),
                    pr["isDraft"],
                    frozenset(label["name"] for label in pr["labels"]["nodes"]),
                )
                for pr in pulls["nodes"]
            ]
        return Snapshot(ready, tuple(reviews))

    @staticmethod
    def merge_state(pr: dict[str, Any]) -> Readiness:
        if pr["mergeable"] == GITHUB_CONFLICTING:
            return Readiness.CONFLICT
        if GITHUB_UNKNOWN in (pr["mergeable"], pr["mergeStateStatus"]):
            return Readiness.UNKNOWN
        if pr["mergeStateStatus"] in GITHUB_QUEUE_READY:
            return Readiness.QUEUE_READY
        return Readiness.PENDING

    def read_review_state(self, repo: str, number: int) -> ReviewState:
        pull = parse_json(self.api(f"repos/{repo}/pulls/{number}"))
        if pull["merged"]:
            return ReviewState.MERGED
        return ReviewState(pull["state"])


def filter_value(value: str) -> str:
    """A value quoted for GitHub's project filter. The filter has no escape character (a
    backslash is literal) but takes double or single quotes, so a value holding one kind is
    wrapped in the other."""
    # UNVERIFIED: that a single-quoted value holding a double quote matches; only plain
    # single-quoted values were checked against a live board.
    if '"' not in value:
        return f'"{value}"'
    if "'" not in value:
        return f"'{value}'"
    raise WatchError(
        f"the lane {value!r} holds both a double and a single quote, which GitHub's project "
        "filter cannot express; rename the Status option and the registry's lane",
        EXIT_BAD_INPUT,
    )


def github_author(node: dict[str, Any]) -> str | None:
    """A GraphQL node's author login; null for a deleted account."""
    return node["author"]["login"] if node["author"] else None


class GitLab(Tracker):
    """GitLab issue boards, in label or Status lane mode (`references/trackers/gitlab.md`):
    REST for label lanes and merge requests (every page), one GraphQL query for Status lanes."""

    cli = "glab"

    def read_login(self) -> str:
        return str(parse_json(self.api("user"))["username"])

    def ndjson(self, path: str) -> list[dict[str, Any]]:
        out = self.api("--paginate", "--output", "ndjson", path)
        return [parse_json(line) for line in out.splitlines() if line.strip()]

    def read_snapshot(self) -> Snapshot:
        reviews: list[Review] = []
        for remote in self.config.repos:
            mrs = self.ndjson(
                f"projects/{encode(remote)}/merge_requests?state=opened&per_page={PAGE}"
                f"&author_username={encode(self.login)}"
            )
            reviews += [
                Review(
                    Item(remote, mr["iid"], mr["title"], mr["web_url"], gitlab_author(mr)),
                    self.merge_state(mr),
                    mr["draft"],
                    frozenset(mr["labels"]),
                )
                for mr in mrs
            ]
        return Snapshot(self.ready(), tuple(reviews))

    def ready(self) -> tuple[Item, ...]:
        board = self.config.board
        if self.config.lane_mode == registry.LaneMode.STATUS:
            return self.ready_by_status(board.path)
        scope = f"{board.scope}s"  # the registry's group or project, which it checks
        issues = self.ndjson(
            f"{scope}/{encode(board.path)}/issues?state=opened&per_page={PAGE}"
            f"&labels={encode(self.config.ready_lane)}"
        )
        return tuple(
            Item(issue["references"]["full"].rsplit("#", 1)[0], issue["iid"], issue["title"],
                 issue["web_url"], gitlab_author(issue))
            for issue in issues
        )  # fmt: skip

    def ready_by_status(self, path: str) -> tuple[Item, ...]:
        query = (
            "query($path: ID!, $lane: String) { namespace(fullPath: $path) {\n"
            "  workItems(state: opened, types: [ISSUE], includeDescendants: true,\n"
            f"            status: {{name: $lane}}, first: {PAGE}) {{\n"
            "    pageInfo { hasNextPage }\n"
            "    nodes { iid title webUrl author { username } namespace { fullPath } } } } }\n"
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
            Item(node["namespace"]["fullPath"], int(node["iid"]), node["title"], node["webUrl"],
                 gitlab_author(node))
            for node in items["nodes"]
        )  # fmt: skip

    @staticmethod
    def merge_state(mr: dict[str, Any]) -> Readiness:
        status = mr["detailed_merge_status"]
        if mr["has_conflicts"] or status == GITLAB_CONFLICT:
            return Readiness.CONFLICT
        if status in GITLAB_UNKNOWN:
            return Readiness.UNKNOWN
        if status == GITLAB_QUEUE_READY:
            return Readiness.QUEUE_READY
        return Readiness.PENDING

    def read_review_state(self, repo: str, number: int) -> ReviewState:
        state = parse_json(self.api(f"projects/{encode(repo)}/merge_requests/{number}"))["state"]
        return ReviewState.OPEN if state in GITLAB_OPEN_STATES else ReviewState(state)


def gitlab_author(node: dict[str, Any]) -> str | None:
    """A GitLab object's author username; null for a deleted account."""
    return node["author"]["username"] if node["author"] else None


TRACKERS: dict[type[registry.Board], type[Tracker]] = {
    registry.GitHubBoard: GitHub,
    registry.GitLabBoard: GitLab,
}


def tick(tracker: Tracker, memory: Memory) -> tuple[list[tuple[Event, Item]], Memory]:
    """Read the tracker once; return the events not printed before and the memory after them.

    The memory is returned, not changed in place, so a tick that fails part way prints nothing
    and forgets nothing."""
    snapshot = tracker.snapshot()
    holding: dict[Event, dict[str, Item]] = {event: {} for event in CONDITION_EVENTS}
    holding[Event.NEW_READY] = {item.key: item for item in snapshot.ready}
    # A review whose state is unknown this tick (being recomputed, or missing from the open
    # list while still open) keeps what it held, so its event does not fire a second time.
    unsure: list[Item] = []
    for review in snapshot.reviews:
        readiness = tracker.readiness(review)
        if readiness is Readiness.UNKNOWN:
            unsure.append(review.item)
        elif event := READINESS_EVENT.get(readiness):
            holding[event][review.item.key] = review.item
    open_after = {review.item.key: review.item for review in snapshot.reviews}
    merged: list[Item] = []
    for key, item in memory.open_reviews.items():
        if key in open_after:
            continue
        state = tracker.state_of(item)
        if state is ReviewState.MERGED:
            merged.append(item)
        elif state is ReviewState.OPEN:
            open_after[key] = item
            unsure.append(item)
    for item in unsure:
        for event in READINESS_EVENT.values():
            if item.key in memory.active[event]:
                holding[event][item.key] = item
    events = [
        (event, item)
        for event, items in holding.items()
        for key, item in items.items()
        if key not in memory.active[event]
    ]
    events += [(Event.MERGED, item) for item in merged]
    return events, Memory({event: frozenset(items) for event, items in holding.items()}, open_after)


def event_line(event: Event, item: Item) -> str:
    return f"{event} {json.dumps(asdict(item), ensure_ascii=False)}"


def memory_path(data_dir: Path, board: registry.Board) -> Path:
    # safe_name folds every separator into '-', so `a/b` board 4 and `a-b` board 4 would share
    # a file (and its lock); a short hash of the exact key keeps them apart.
    digest = hashlib.sha256(board.key.encode()).hexdigest()[:8]
    return data_dir / "state" / f"board-watcher-{safe_name(board.key)}-{digest}.json"


def watch(
    tracker: Tracker, path: Path, interval: int, once: bool, sleep: Callable[[float], None]
) -> int:
    """Sign in and watch, holding the memory file's lock for the whole run, so a second watcher
    on the same board and data folder is refused (before it calls the tracker at all) instead of
    printing every event a second time."""
    try:
        with locked(path, wait=False):
            tracker.sign_in()
            return loop(tracker, path, interval, once, sleep)
    except LockHeld as err:
        raise WatchError(
            f"another watcher already watches board {tracker.config.board.key} from this data "
            f"folder ({err}); read its output, or stop it before starting this one",
            EXIT_ALREADY_WATCHING,
        ) from err


def loop(
    tracker: Tracker, path: Path, interval: int, once: bool, sleep: Callable[[float], None]
) -> int:
    memory = Memory.load(path)
    while True:
        try:
            events, after = tick(tracker, memory)
        except TrackerError as err:
            if AUTH_FAILURE.search(str(err)):
                raise WatchError(tracker.auth_message(err), EXIT_AUTH) from err
            # Anything else (the network, a rate limit, a 5xx) is retried on the next tick.
            print(f"watch_board.py: the tick failed: {err}", file=sys.stderr, flush=True)
            if once:
                return EXIT_TICK_FAILED
        else:
            for event, item in events:
                print(event_line(event, item), flush=True)
            # Printed before saved: a crash between the two prints those events again on
            # restart (at least once), never loses one.
            save(path, after.to_json())
            memory = after
        if once:
            return 0
        sleep(interval)


def main(argv: list[str], run: Run = run_cli, sleep: Callable[[float], None] = time.sleep) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--data-dir", required=True, type=Path, help="the plugin's data folder")
    parser.add_argument(
        "--interval", type=int, default=DEFAULT_INTERVAL,
        help=f"seconds between ticks (default {DEFAULT_INTERVAL}, at least {MIN_INTERVAL})",
    )  # fmt: skip
    # For a scheduler, and for a quick look at what the board holds now.
    parser.add_argument("--once", action="store_true", help="run one tick, then exit")
    args = parser.parse_args(argv)
    if args.interval < MIN_INTERVAL:
        print(f"error: --interval must be at least {MIN_INTERVAL} seconds", file=sys.stderr)
        return EXIT_BAD_INPUT
    data_dir = args.data_dir.expanduser()

    code, payload, reg = registry.ensure(data_dir)
    if reg is None:
        print(json.dumps(payload, indent=2), file=sys.stderr)
        # registry.py's bad input (its example file missing from the plugin) stays bad input.
        return EXIT_BAD_INPUT if code == registry.EXIT_BAD_INPUT else EXIT_REGISTRY
    config = Config.from_registry(reg)
    tracker = TRACKERS[type(config.board)](config, run)
    try:
        return watch(tracker, memory_path(data_dir, config.board), args.interval, args.once, sleep)
    except WatchError as err:
        print(err if err.code == EXIT_AUTH else f"error: {err}", file=sys.stderr)
        return err.code
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
