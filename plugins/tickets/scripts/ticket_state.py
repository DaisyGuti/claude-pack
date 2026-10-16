#!/usr/bin/env python3
"""Keep the work-tickets run record: what is running, in review, blocked or skipped.

One JSON file per (board, signed-in login) lives in the plugin's data folder. The
`work-tickets` skill is its only writer: workers return a result and the skill records it
here. The file lets a run that was cut off resume its unfinished tickets, keeps "skipped"
between runs, and lets `--dry-run` list reviews still open from earlier runs. Every
read-modify-write takes an exclusive lock, so a second run on the same board and login waits
instead of corrupting the file.

Usage:
    ticket_state.py COMMAND --data-dir DIR --board-key KEY --login LOGIN [options]

Commands:
    init                          create the file if missing; print its path
    show                          print the whole record
    set-project --json JSON       store the board facts; refuses a different board or login
    next-slot                     print the smallest unused slot number as 'slot-N'
    begin --json JSON             add a slot to active (a ticket already tracked is refused)
    finish --json JSON            move a slot out of active by its result status
    skip --number N --repo R --reason T
    clear-skipped
    forget --number N --repo R    drop a ticket from completed/blocked so it can be retried

Exit codes: 0 ok, 2 bad input or a state file this script does not understand, 3 refused
(duplicate ticket, or the file belongs to another board or login).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

if sys.version_info < (3, 11):  # noqa: UP036  (a clear message on an older python3)
    sys.exit("ticket_state.py needs Python 3.11 or newer; install it and run this again")

try:
    import fcntl
except ImportError:  # no flock on this platform; a single run at a time is then the user's job
    fcntl = None  # type: ignore[assignment]  # stdlib module is absent on Windows only

SCHEMA_VERSION = 1
EXIT_BAD_INPUT = 2
EXIT_REFUSED = 3
# A finished worker run ends in exactly one of these; anything else is a protocol error.
STATUS_COMPLETED = "review_opened"
STATUS_BLOCKED_PREFIXES = ("blocked_",)
STATUS_BLOCKED_EXACT = ("needs_decision", "needs_manual_action")


class StateError(Exception):
    """A problem the caller can fix; carries the exit code."""

    def __init__(self, message: str, code: int = EXIT_BAD_INPUT) -> None:
        super().__init__(message)
        self.code = code


def safe_name(value: str) -> str:
    """Make a board key or login safe as a file name part."""
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")


def state_path(data_dir: Path, board_key: str, login: str) -> Path:
    return data_dir / "state" / f"ready-worker-{safe_name(board_key)}-{safe_name(login)}.json"


def empty_state() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "project": {},
        "active": [],
        "completed": [],
        "blocked": [],
        "skipped": [],
    }


@contextlib.contextmanager
def locked(path: Path) -> Iterator[None]:
    """Hold an exclusive advisory lock on `<state file>.lock` for the duration."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with open(lock_path, "w", encoding="utf-8") as handle:
        if fcntl is not None:
            fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(handle, fcntl.LOCK_UN)


def load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return empty_state()
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as err:
        raise StateError(
            f"{path} is not valid JSON ({err}); delete it to start a fresh record"
        ) from err
    if state.get("schema_version") != SCHEMA_VERSION:
        raise StateError(
            f"{path} has schema_version {state.get('schema_version')!r}; this script reads "
            f"{SCHEMA_VERSION}. Delete the file to start a fresh record."
        )
    return state


def save(path: Path, state: dict[str, Any]) -> None:
    """Write atomically so a crash never leaves half a file."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2)
            handle.write("\n")
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise


def key_of(entry: dict[str, Any]) -> tuple[int, str]:
    """Issue numbers repeat across repos, so a ticket is always the pair (number, repo)."""
    return int(entry["ticket_number"]), str(entry["ticket_repo"])


def tracked(state: dict[str, Any], number: int, repo: str) -> str | None:
    for bucket in ("active", "completed", "blocked"):
        for entry in state[bucket]:
            if key_of(entry) == (number, repo):
                return bucket
    return None


def require(entry: dict[str, Any], fields: tuple[str, ...], what: str) -> None:
    missing = [f for f in fields if f not in entry]
    if missing:
        raise StateError(f"{what} is missing {', '.join(missing)}")


def next_slot(state: dict[str, Any]) -> str:
    """Smallest positive slot number not used by an active or blocked slot (blocked slots keep
    their worktrees, so their ids stay taken)."""
    used = {
        int(e["slot_id"].removeprefix("slot-"))
        for e in (*state["active"], *state["blocked"])
        if str(e.get("slot_id", "")).startswith("slot-")
    }
    number = 1
    while number in used:
        number += 1
    return f"slot-{number}"


def apply(state: dict[str, Any], command: str, args: argparse.Namespace) -> Any:
    """Run one command against `state` in memory; return what to print (or None)."""
    if command == "set-project":
        project = json.loads(args.json)
        current = state["project"]
        for field in ("board_key", "assignee"):
            if current.get(field) and project.get(field) != current[field]:
                raise StateError(
                    f"this record belongs to {field} {current[field]!r} and the request names "
                    f"{project.get(field)!r}; two boards or two people must not share one record",
                    EXIT_REFUSED,
                )
        state["project"] = project
    elif command == "next-slot":
        return next_slot(state)
    elif command == "begin":
        slot = json.loads(args.json)
        require(slot, ("slot_id", "ticket_number", "ticket_repo"), "slot")
        where = tracked(state, *key_of(slot))
        if where:
            raise StateError(
                f"ticket {slot['ticket_repo']}#{slot['ticket_number']} is already in {where}",
                EXIT_REFUSED,
            )
        state["active"].append({**slot, "status": "running"})
    elif command == "finish":
        result = json.loads(args.json)
        require(result, ("slot_id", "status"), "result")
        status = result["status"]
        completed = status == STATUS_COMPLETED
        blocked = status in STATUS_BLOCKED_EXACT or status.startswith(STATUS_BLOCKED_PREFIXES)
        if not (completed or blocked):
            raise StateError(
                f"status {status!r} is not a finished state; use review_opened, needs_decision, "
                "needs_manual_action or blocked_<reason>"
            )
        index = next(
            (i for i, e in enumerate(state["active"]) if e["slot_id"] == result["slot_id"]), None
        )
        if index is None:
            raise StateError(f"no active slot {result['slot_id']!r}")
        entry = {**state["active"].pop(index), **result}
        state["completed" if completed else "blocked"].append(entry)
    elif command == "skip":
        entry = {"ticket_number": args.number, "ticket_repo": args.repo, "reason": args.reason}
        for index, existing in enumerate(state["skipped"]):
            if key_of(existing) == (args.number, args.repo):
                state["skipped"][index] = entry  # the latest reason replaces an older one
                break
        else:
            state["skipped"].append(entry)
    elif command == "clear-skipped":
        state["skipped"] = []
    elif command == "forget":
        for bucket in ("completed", "blocked"):
            state[bucket] = [e for e in state[bucket] if key_of(e) != (args.number, args.repo)]
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "command",
        choices=(
            "init",
            "show",
            "set-project",
            "next-slot",
            "begin",
            "finish",
            "skip",
            "clear-skipped",
            "forget",
        ),  # fmt: skip
    )
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--board-key", required=True)
    parser.add_argument("--login", required=True)
    parser.add_argument("--json", help="JSON payload for set-project, begin and finish")
    parser.add_argument("--number", type=int)
    parser.add_argument("--repo")
    parser.add_argument("--reason")
    return parser


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    path = state_path(args.data_dir.expanduser(), args.board_key, args.login)
    needs = {
        "set-project": ("json",), "begin": ("json",), "finish": ("json",),
        "skip": ("number", "repo", "reason"), "forget": ("number", "repo"),
    }  # fmt: skip
    for field in needs.get(args.command, ()):
        if getattr(args, field) is None:
            print(f"error: {args.command} needs --{field}", file=sys.stderr)
            return EXIT_BAD_INPUT
    try:
        with locked(path):
            state = load(path)
            output = apply(state, args.command, args)
            if args.command not in ("show", "next-slot"):
                save(path, state)
    except StateError as err:
        print(f"error: {err}", file=sys.stderr)
        return err.code
    except json.JSONDecodeError as err:
        print(f"error: --json is not valid JSON ({err})", file=sys.stderr)
        return EXIT_BAD_INPUT
    if args.command == "show":
        print(json.dumps(state, indent=2))
    elif args.command == "init":
        print(path)
    elif output is not None:
        print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
