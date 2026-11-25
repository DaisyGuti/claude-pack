#!/usr/bin/env python3
"""Find the dependency holds on a board that can never clear, or should already have.

`daily-grooming` step 3 hands this script the board as `links.py fetch` writes it: every open
ticket with its native blocked-by links (`blocked_by`), and every issue those links name. A
ticket depends on each issue it is blocked by. Two more kinds of edge are implied, because a
ticket closes only after them:

- a tracker waits on its parts: an issue is a tracker when another ticket's body says
  `Part <N> of <M>` on a line naming it (`Part 2 of 5, cut by layer from #12`), or when its
  input entry lists `parts`;
- a batch parent waits on its children (`children`).

It reports, the same way on every run:

- **cycles**: each chain of edges that leads back to where it started, so none of its tickets
  can ever move;
- **tracker dependencies**: a blocked-by link to a tracker or a batch parent, which closes
  last. It names the open parts (or children) to link instead, and `name_instead` when exactly
  one is open;
- **merged dependencies**: a blocked-by link to an open issue a merged review `Refs`
  (**merged-reviews**): some or all of its work is on the default branch, so a person checks
  whether the issue is done before anything keeps waiting on it;
- **cleared**: an open ticket whose every blocker is closed;
- **unknown**: a blocker that is not in the input, which the caller checks with **issue-state**
  and adds before running again.

Usage:
    deps.py TICKETS_FILE

TICKETS_FILE is JSON: {"tickets": [{"ref", "repo", "state", "title", "body", "blocked_by": [...],
"parts": [...], "children": [...], "merged_reviews": [...]}]}. `ref` is `#<n>` or `<repo>#<n>`;
`repo` is the registry Remote (`owner/repo`, `group/sub/project`); `state` is `open` or `closed`.
Only `ref`, `repo` and `state` are required: a closed blocker needs nothing else. A ref is `#<n>`
(the ticket's own repo), `<repo>#<n>` (a bare project name takes the ticket's owner) or an
issue URL (`.../issues/<n>`, `.../-/issues/<n>`, `.../-/work_items/<n>`). The body is read
only for `Part <N> of <M>` lines; a dependency written in a body is not one until
`links.py migrate` links it. `merged_reviews` lists the URLs **merged-reviews** printed for an
open issue. A ref listed twice is bad input.

Prints JSON {"cycles": [[{"from", "to", "via"}]], "tracker_dependencies": [{"ticket", "names",
"kind", "open_parts", "name_instead"}], "merged_dependencies": [{"ticket", "names", "reviews"}],
"cleared": [{"ticket", "blocked_by"}], "unknown": [ref, ...]}. Every ref is printed as
`<repo>#<n>`. `via` is `blocked by`, `part` or `child`. Exit codes: 0 printed, 2 bad input.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

if sys.version_info < (3, 11):  # noqa: UP036  (a clear message on an older python3)
    sys.exit("deps.py needs Python 3.11 or newer; install it and run this again")

# The line a part carries (plan-one-ticket.md step 2): "Part 2 of 5, cut by layer from #12".
PART_LINE = re.compile(r"\bpart\s+(\d+)\s+of\s+\d+\b", re.IGNORECASE)
# An issue URL on GitHub (`/issues/<n>`) or GitLab (`/-/issues/<n>`, `/-/work_items/<n>`).
ISSUE_URL = re.compile(
    r"https?://[^/\s]+/(?P<repo>[\w.-]+(?:/[\w.-]+)*?)(?:/-)?/(?:issues|work_items)/(?P<n>\d+)"
)
# Any other URL is not a ticket ref (`.../merge_requests/4`, a `#fragment`).
OTHER_URL = re.compile(r"https?://\S+")
# `#12`, `app#12` or `group/app#12`, not inside a word.
SHORT_REF = re.compile(r"(?<![\w/#.-])(?P<repo>[\w.-]*\w(?:/[\w.-]*\w)*)?(?<![.-])#(?P<n>\d+)\b")
OPEN, CLOSED = "open", "closed"


class Via(Enum):
    """Why one ticket waits on another."""

    BLOCKED_BY = "blocked by"
    PART = "part"
    CHILD = "child"


@dataclass(frozen=True)
class Ticket:
    """One input entry, parsed once."""

    ref: str
    open: bool
    blocked_by: tuple[str, ...]
    part_of: tuple[tuple[str, int], ...]  # (tracker ref, part number) from its body
    parts: tuple[str, ...]
    children: tuple[str, ...]
    merged_reviews: tuple[str, ...]


def qualify(repo: str, named: str | None) -> str:
    """The ticket's repo, or the one a ref names (a bare name shares the ticket repo's owner)."""
    if not named:
        return repo.lower()
    owner = repo.rpartition("/")[0]
    return (named if "/" in named or not owner else f"{owner}/{named}").lower()


def ref_key(repo: str, text: str) -> str:
    """One spelling for a ref the input writes as `#<n>`, `<repo>#<n>` or a URL."""
    refs = refs_in(repo, text)
    if len(refs) != 1:
        raise ValueError(f"not one issue ref: {text!r}")
    return refs[0]


def refs_in(repo: str, text: str) -> list[str]:
    """Every issue ref in a piece of text, in order, each once."""
    found = [f"{qualify(repo, m['repo'])}#{m['n']}" for m in ISSUE_URL.finditer(text)]
    rest = OTHER_URL.sub(" ", ISSUE_URL.sub(" ", text))
    found += [f"{qualify(repo, m['repo'])}#{m['n']}" for m in SHORT_REF.finditer(rest)]
    return list(dict.fromkeys(found))


def string_list(entry: dict[str, object], key: str) -> list[str]:
    value = entry.get(key, [])
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValueError(f"ticket {entry.get('ref')!r}: {key} must be a list of strings")
    return list(value)


def parse_ticket(entry: dict[str, object]) -> Ticket:
    """Read one input entry; a missing or malformed field raises ValueError."""
    missing = [k for k in ("ref", "repo", "state") if not isinstance(entry.get(k), str)]
    if missing:
        raise ValueError(f"ticket {entry.get('ref')!r}: missing {', '.join(missing)}")
    repo, state = str(entry["repo"]), str(entry["state"])
    if state not in (OPEN, CLOSED):
        raise ValueError(f"ticket {entry['ref']!r}: state must be open or closed, not {state!r}")
    body = entry.get("body", "")
    if not isinstance(body, str):
        raise ValueError(f"ticket {entry['ref']!r}: body must be a string")
    ref = ref_key(repo, str(entry["ref"]))
    part_of: list[tuple[str, int]] = []
    for line in body.splitlines():
        if (part := PART_LINE.search(line)) and (named := refs_in(repo, line)):
            part_of.append((named[0], int(part.group(1))))
    blocked_by = [ref_key(repo, b) for b in string_list(entry, "blocked_by")]
    return Ticket(
        ref=ref,
        open=state == OPEN,
        blocked_by=tuple(r for r in dict.fromkeys(blocked_by) if r != ref),
        part_of=tuple(p for p in part_of if p[0] != ref),
        parts=tuple(ref_key(repo, p) for p in string_list(entry, "parts")),
        children=tuple(ref_key(repo, c) for c in string_list(entry, "children")),
        merged_reviews=tuple(string_list(entry, "merged_reviews")),
    )


@dataclass(frozen=True)
class Board:
    """The tickets by ref, and every edge between open tickets."""

    tickets: dict[str, Ticket]
    part_numbers: dict[str, dict[str, int]]  # tracker -> {part ref: number}
    edges: dict[str, list[tuple[str, Via]]]

    def is_open(self, ref: str) -> bool:
        ticket = self.tickets.get(ref)
        return ticket is not None and ticket.open

    def waits_on(self, ref: str) -> list[tuple[str, Via]]:
        """What an open ticket still waits on: its open dependencies, parts and children."""
        return [(to, via) for to, via in self.edges.get(ref, []) if self.is_open(to)]


def build_board(tickets: list[Ticket]) -> Board:
    by_ref = {t.ref: t for t in tickets}
    part_numbers: dict[str, dict[str, int]] = {}
    for ticket in tickets:
        for tracker, number in ticket.part_of:
            part_numbers.setdefault(tracker, {})[ticket.ref] = number
        for n, part in enumerate(ticket.parts, start=1):
            part_numbers.setdefault(ticket.ref, {}).setdefault(part, n)
    edges: dict[str, list[tuple[str, Via]]] = {}
    for ticket in tickets:
        out = [(d, Via.BLOCKED_BY) for d in ticket.blocked_by]
        out += [(p, Via.PART) for p in part_numbers.get(ticket.ref, {})]
        out += [(c, Via.CHILD) for c in ticket.children]
        edges[ticket.ref] = out
    return Board(by_ref, part_numbers, edges)


def find_cycles(board: Board) -> list[list[tuple[str, str, Via]]]:
    """One cycle per group of open tickets that wait on each other (Tarjan's components).

    Each cycle starts at its group's lowest ref and is the shortest way back to it, so the same
    board prints the same cycles.
    """
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    groups: list[set[str]] = []

    def visit(start: str) -> None:
        # Iterative, so a long chain of holds cannot hit the recursion limit.
        work = [(start, iter(board.waits_on(start)))]
        index[start] = low[start] = len(index)
        stack.append(start)
        on_stack.add(start)
        while work:
            ref, targets = work[-1]
            advanced = False
            for to, _ in targets:
                if to not in index:
                    index[to] = low[to] = len(index)
                    stack.append(to)
                    on_stack.add(to)
                    work.append((to, iter(board.waits_on(to))))
                    advanced = True
                    break
                if to in on_stack:
                    low[ref] = min(low[ref], index[to])
            if advanced:
                continue
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[ref])
            if low[ref] == index[ref]:
                group: set[str] = set()
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    group.add(member)
                    if member == ref:
                        break
                if len(group) > 1:
                    groups.append(group)

    for ref in sorted(r for r, t in board.tickets.items() if t.open):
        if ref not in index:
            visit(ref)
    return sorted((shortest_cycle(board, g) for g in groups), key=lambda c: c[0][0])


def shortest_cycle(board: Board, group: set[str]) -> list[tuple[str, str, Via]]:
    """The shortest path from the group's lowest ref back to itself, inside the group."""
    start = min(group)
    came_from: dict[str, tuple[str, Via]] = {}
    queue = [start]
    while queue:
        ref = queue.pop(0)
        for to, via in sorted(board.waits_on(ref), key=lambda e: e[0]):
            if to not in group or to in came_from:
                continue
            came_from[to] = (ref, via)
            if to == start:
                queue.clear()
                break
            queue.append(to)
    path: list[tuple[str, str, Via]] = []
    ref = start
    while True:
        before, via = came_from[ref]
        path.append((before, ref, via))
        ref = before
        if ref == start:
            return path[::-1]


def report(board: Board) -> dict[str, object]:
    tracker_deps: list[dict[str, object]] = []
    merged_deps: list[dict[str, object]] = []
    cleared: list[dict[str, object]] = []
    unknown: set[str] = set()
    for ref in sorted(board.tickets):
        ticket = board.tickets[ref]
        if not ticket.open:
            continue
        for dep in ticket.blocked_by:
            target = board.tickets.get(dep)
            if target is None:
                unknown.add(dep)
                continue
            if not target.open:
                continue
            numbers = board.part_numbers.get(dep, {})
            kind, members = (
                ("tracker", sorted(numbers, key=numbers.__getitem__))
                if numbers
                else ("batch parent", sorted(target.children))
            )
            if members:
                open_members = [m for m in members if board.is_open(m) and m != ref]
                tracker_deps.append(
                    {
                        "ticket": ref,
                        "names": dep,
                        "kind": kind,
                        "open_parts": open_members,
                        "name_instead": open_members[0] if len(open_members) == 1 else None,
                    }
                )
            if target.merged_reviews:
                merged_deps.append(
                    {"ticket": ref, "names": dep, "reviews": list(target.merged_reviews)}
                )
        known = [d for d in ticket.blocked_by if d in board.tickets]
        all_known = bool(ticket.blocked_by) and len(known) == len(ticket.blocked_by)
        if all_known and not any(board.is_open(d) for d in known):
            cleared.append({"ticket": ref, "blocked_by": list(ticket.blocked_by)})
    return {
        "cycles": [
            [{"from": a, "to": b, "via": via.value} for a, b, via in cycle]
            for cycle in find_cycles(board)
        ],
        "tracker_dependencies": tracker_deps,
        "merged_dependencies": merged_deps,
        "cleared": cleared,
        "unknown": sorted(unknown),
    }


def load(path: Path) -> Board:
    """Read and check the tickets file; any problem raises ValueError or OSError."""
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("tickets") if isinstance(data, dict) else None
    if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
        raise ValueError('expected {"tickets": [ {...}, ... ]}')
    tickets = [parse_ticket(entry) for entry in entries]
    refs = [t.ref for t in tickets]
    if repeated := sorted({r for r in refs if refs.count(r) > 1}):
        raise ValueError(f"listed more than once: {repeated}")
    return build_board(tickets)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tickets_file", type=Path)
    args = parser.parse_args(argv)
    try:
        board = load(args.tickets_file)
    except (OSError, ValueError) as exc:
        print(f"deps.py: {args.tickets_file}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report(board), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
