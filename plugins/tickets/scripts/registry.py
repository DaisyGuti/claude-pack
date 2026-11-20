#!/usr/bin/env python3
"""Read, create and check the team's ticket registry.

The registry is a Markdown file the user edits: tracker, board, lanes, priorities, labels,
model labels and repos. It lives in the plugin's data folder (`${CLAUDE_PLUGIN_DATA}`), which
survives plugin updates; the plugin ships only `registry.example.md`. Skills call this script
instead of reading the tables themselves so a lane or label is looked up the same way every time.

Usage:
    registry.py ensure --data-dir DIR          create the file on first run, then check it
    registry.py show --data-dir DIR            print the parsed registry as JSON (after ensure)
    registry.py board-url URL --data-dir DIR   resolve a pasted board URL to owner/number or path/id

Exit codes: 0 ok, 2 bad input, 3 registry created just now (user must fill it in),
4 registry incomplete, 5 board URL host differs from the registry's host.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections.abc import Callable
from dataclasses import MISSING, asdict, dataclass, fields, replace
from enum import StrEnum
from pathlib import Path
from typing import Any, ClassVar

if sys.version_info < (3, 11):  # noqa: UP036
    sys.exit("registry.py needs Python 3.11 or newer; install it and run this again")

EXAMPLE = Path(__file__).resolve().parent.parent / "registry.example.md"
REGISTRY_NAME = "registry.md"

EXIT_BAD_INPUT = 2
EXIT_CREATED = 3
EXIT_INCOMPLETE = 4
EXIT_HOST_MISMATCH = 5

REQUIRED_LANES = ("backlog", "ready", "in_progress", "blocked", "done")
REQUIRED_LABELS = ("blocked", "run_worker", "run_solo")
TIERS = ("fast", "workhorse", "frontier")


class Tracker(StrEnum):
    GITHUB = "github"
    GITLAB = "gitlab"


class Scope(StrEnum):
    """What a GitLab board belongs to."""

    GROUP = "group"
    PROJECT = "project"


class LaneMode(StrEnum):
    """How a GitLab board holds its lanes: scoped labels (the default) or the work item Status."""

    LABELS = "labels"
    STATUS = "status"


# The Board section's `Key: value` lines, one model per tracker. A field's name is its key in
# lower case; a field with no default is required, and `problems()` names it when it is empty.
@dataclass(frozen=True)
class GitHubBoard:
    """A GitHub Projects (v2) board: the owning user or organization and the project number."""

    heading: ClassVar[str] = "GitHub"

    owner: str
    number: str
    name: str = ""

    @property
    def key(self) -> str:
        return f"{self.owner}/{self.number}"


@dataclass(frozen=True)
class GitLabBoard:
    """A GitLab issue board: its group or project, and its name or id."""

    heading: ClassVar[str] = "GitLab"

    scope: str  # a Scope; kept as written so problems() can name a wrong one
    path: str
    board: str
    # A LaneMode, kept as written likewise. A registry written before the Lanes key existed
    # keeps label lanes.
    lanes: str = LaneMode.LABELS

    @property
    def key(self) -> str:
        return f"{self.path}/{self.board}"


Board = GitHubBoard | GitLabBoard


# Each tracker's board model; any other tracker name reads the GitLab subsection, and
# problems() refuses it.
BOARDS: dict[str, type[Board]] = {Tracker.GITHUB: GitHubBoard, Tracker.GITLAB: GitLabBoard}
TRACKERS = tuple(Tracker)
# Where batch parents live: a GitLab group epic, a GitHub sub-issue parent, a shared
# `batch:<area>` label on either tracker, or no batches at all (every ticket a single).
BATCH_MODES = {
    "off": TRACKERS,
    "epics": (Tracker.GITLAB,),
    "sub-issues": (Tracker.GITHUB,),
    "labels": TRACKERS,
}
DEFAULT_BATCH_SIZE = 5
# Values that ship in registry.example.md. A board or repo that still holds one was never filled in.
EXAMPLE_MARKERS = ("your-github-login", "your-group")


def read_board(cls: type[Board], values: dict[str, str]) -> Board:
    """Build a board from its `Key: value` lines. A missing required key reads as empty (for
    `problems()` to name); a missing optional one takes its default; unknown keys are dropped."""
    given = {
        f.name: values.get(f.name, "")
        for f in fields(cls)
        if f.name in values or f.default is MISSING
    }
    return cls(**given)


def missing_board_keys(board: Board) -> list[str]:
    """The required board keys with no value."""
    return [f.name for f in fields(board) if f.default is MISSING and not getattr(board, f.name)]


def sections(text: str, level: int) -> dict[str, str]:
    """Split Markdown into {heading: body} for headings of exactly `level` hashes."""
    marker = "#" * level + " "
    found: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        if line.startswith(marker):
            current = line[len(marker) :].strip()
            found[current] = []
        elif line.startswith("#" * (level - 1) + " ") and level > 1:
            current = None
        elif current is not None:
            found[current].append(line)
    return {name: "\n".join(lines) for name, lines in found.items()}


def clean(cell: str) -> str:
    """Strip a table cell or value of surrounding whitespace and backticks."""
    return cell.strip().strip("`").strip()


def key_values(body: str) -> dict[str, str]:
    """Read '- Key: `value`' bullet lines into a dict keyed by lower-case key."""
    values: dict[str, str] = {}
    for line in body.splitlines():
        match = re.match(r"^\s*-\s+([A-Za-z ]+?):\s*(.+?)\s*$", line)
        if match:
            values[match.group(1).strip().lower()] = clean(match.group(2).split(" (")[0])
    return values


def table(body: str) -> list[dict[str, str]]:
    """Read the first Markdown table in `body` into rows keyed by lower-case header."""
    rows: list[list[str]] = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            rows.append([c.strip() for c in stripped.strip("|").split("|")])
        elif rows:
            break
    if len(rows) < 2:
        return []
    headers = [h.lower() for h in rows[0]]
    return [
        {headers[i]: clean(cell) for i, cell in enumerate(row) if i < len(headers)}
        for row in rows[2:]
        if any(clean(c) for c in row)
    ]


def column(row: dict[str, str], tracker: str) -> str:
    """Pick the tracker's value from a row whose headers read 'GitHub (...)' or 'GitLab (...)'."""
    for header, value in row.items():
        if header.startswith(tracker):
            return value
    return ""


def parse(text: str, home: Path | None = None) -> dict[str, Any]:
    """Turn the registry Markdown into a dict. Missing parts come back empty, never invented."""
    top = sections(text, 2)
    tracker_vals = key_values(top.get("Tracker", ""))
    tracker = tracker_vals.get("tracker", "").lower()
    board_sections = sections("## Board\n" + top.get("Board", ""), 3)
    board_type = BOARDS.get(tracker, GitLabBoard)
    board = read_board(board_type, key_values(board_sections.get(board_type.heading, "")))
    if isinstance(board, GitLabBoard):
        # Scope and Lanes are matched as lower case, however the user wrote them.
        board = replace(board, scope=board.scope.lower(), lanes=board.lanes.lower())

    lanes: dict[str, str] = {}
    lane_meaning: dict[str, str] = {}
    for row in table(top.get("Lanes", "")):
        lanes[row.get("role", "")] = column(row, tracker)
        lane_meaning[row.get("role", "")] = row.get("meaning", "")

    priorities = [
        {
            "role": row.get("role", ""),
            "value": column(row, tracker),
            "meaning": row.get("meaning", ""),
        }
        for row in table(top.get("Priority", ""))
    ]
    labels = {
        row.get("role", ""): {
            "name": row.get("label", ""),
            "color": row.get("color", ""),
            "description": row.get("description", ""),
        }
        for row in table(top.get("Labels", ""))
    }
    model_labels = {
        row.get("tier", ""): {"label": row.get("label", ""), "color": row.get("color", "")}
        for row in table(top.get("Model labels", ""))
    }
    batch_vals = key_values(top.get("Batches", ""))
    size = batch_vals.get("batch size", str(DEFAULT_BATCH_SIZE))
    base = home or Path.home()
    repos = [
        {
            "name": row.get("name", ""),
            "remote": row.get("remote", ""),
            "clone": expand(row.get("local clone", ""), base),
            "brief": expand(row.get("product brief", ""), base),
            "focus": row.get("focus", ""),
        }
        for row in table(top.get("Repos", ""))
    ]
    return {
        "tracker": tracker,
        "host": tracker_vals.get("host", ""),
        "works_for": tracker_vals.get("works for", ""),
        "board": board,
        "lane_mode": board.lanes if isinstance(board, GitLabBoard) else None,
        # Without a Batches section every ticket stays a single, as before batching existed.
        "batching": {
            "mode": batch_vals.get("batching", "off").lower(),
            "size": int(size) if size.isdigit() else size,
        },
        "lanes": lanes,
        "lane_meaning": lane_meaning,
        "priorities": priorities,
        "labels": labels,
        "model_labels": model_labels,
        "repos": repos,
    }


def expand(path: str, home: Path) -> str:
    """Expand a leading ~ against `home` so tests do not depend on the real home folder."""
    if path == "~" or path.startswith("~/"):
        return str(home / path[2:]) if path != "~" else str(home)
    return path


def problems(reg: dict[str, Any], which: Callable[[str], str | None] | None = None) -> list[str]:
    """List what stops the registry from being usable. An empty list means it is ready.

    `which` finds a command on PATH and defaults to `shutil.which`.
    """
    which = which or shutil.which
    found: list[str] = []
    in_use = [*asdict(reg["board"]).values(), *(repo["remote"] for repo in reg["repos"])]
    for marker in EXAMPLE_MARKERS:
        if any(marker in value for value in in_use):
            found.append(
                f"the Board or Repos table still holds the example value '{marker}'; "
                "replace it with your own"
            )
    if reg["tracker"] not in TRACKERS:
        found.append(f"Tracker is '{reg['tracker']}'; it must be {one_of(Tracker)}")
    if not reg["host"]:
        found.append("Host is empty; write github.com, gitlab.com or your server's host")
    if reg["tracker"] in TRACKERS:
        for key in missing_board_keys(reg["board"]):
            found.append(f"Board has no '{key}' value for the {reg['tracker']} tracker")
    board = reg["board"]
    gitlab = reg["tracker"] == Tracker.GITLAB
    # An empty Scope is already named as a missing key above.
    if gitlab and board.scope and board.scope not in tuple(Scope):
        found.append(f"Board has Scope '{board.scope}'; it must be {one_of(Scope)}")
    if gitlab and reg["lane_mode"] not in tuple(LaneMode):
        found.append(
            f"Board has Lanes '{reg['lane_mode']}' for the gitlab tracker; "
            f"it must be {one_of(LaneMode)}"
        )
    if gitlab and reg["lane_mode"] == LaneMode.STATUS:
        # The usual slip when a board moves to Status: the mode flips but the column keeps labels.
        for role, value in reg["lanes"].items():
            if "::" in value:
                found.append(
                    f"lane '{role}' is '{value}', a scoped label, but the GitLab board's Lanes "
                    "is 'status'; write the Status name the board shows (for example 'Ready')"
                )
    batch_mode, batch_size = reg["batching"]["mode"], reg["batching"]["size"]
    if batch_mode not in BATCH_MODES:
        found.append(f"Batching is '{batch_mode}'; it must be one of {', '.join(BATCH_MODES)}")
    elif reg["tracker"] in TRACKERS and reg["tracker"] not in BATCH_MODES[batch_mode]:
        found.append(f"Batching '{batch_mode}' does not exist on the {reg['tracker']} tracker")
    if not isinstance(batch_size, int) or batch_size < 1:
        found.append(f"Batch size is '{batch_size}'; it must be a whole number of 1 or more")
    for role in REQUIRED_LANES:
        if not reg["lanes"].get(role):
            found.append(
                f"Lanes has no value for role '{role}' on the {reg['tracker'] or '?'} tracker"
            )
    if not reg["priorities"] or any(not p["value"] for p in reg["priorities"]):
        found.append("Priority table is empty or has a role with no value for this tracker")
    for role in REQUIRED_LABELS:
        if not reg["labels"].get(role, {}).get("name"):
            found.append(f"Labels has no row for role '{role}'")
    for tier in TIERS:
        if not reg["model_labels"].get(tier, {}).get("label"):
            found.append(f"Model labels has no row for tier '{tier}'")
    if not reg["repos"]:
        found.append("Repos table is empty; add at least one repo")
    for repo in reg["repos"]:
        if not repo["name"] or not repo["remote"]:
            found.append("a Repos row is missing its Name or Remote")
        elif not Path(repo["clone"]).is_dir():
            found.append(f"repo '{repo['name']}': local clone '{repo['clone']}' is not a folder")
    for tool, hint in tools_needed(reg["tracker"]):
        if not which(tool):
            found.append(f"'{tool}' is not on PATH: {hint}")
    return found


def one_of(choices: type[StrEnum]) -> str:
    """An enum's values for a message: 'a' or 'b'."""
    return " or ".join(f"'{choice}'" for choice in choices)


def tools_needed(tracker: str) -> list[tuple[str, str]]:
    """The command-line tools a tracker needs, each with how to install it."""
    needed = [("git", "install git 2.31 or newer")]
    if tracker == Tracker.GITHUB:
        needed.append(
            ("gh", "install the GitHub CLI (https://cli.github.com), then run 'gh auth login'")
        )
    elif tracker == Tracker.GITLAB:
        needed.append(
            (
                "glab",
                "install the GitLab CLI (gitlab.com/gitlab-org/cli), then run 'glab auth login'",
            )
        )
        needed.append(("jq", "install jq (macOS ships it; on Linux use your package manager)"))
    return needed


def registry_path(data_dir: Path) -> Path:
    return data_dir / REGISTRY_NAME


def to_json(reg: dict[str, Any]) -> dict[str, Any]:
    """The parsed registry as `show` prints it: the board model becomes its key-value object."""
    return {**reg, "board": asdict(reg["board"])}


def ensure(data_dir: Path) -> tuple[int, dict[str, Any], dict[str, Any] | None]:
    """Create the registry on first run, then check it.

    Returns (exit code, JSON payload, the parsed registry); the registry is None unless the
    code is 0, so a caller reads and parses the file once."""
    path = registry_path(data_dir)
    if not path.exists():
        if not EXAMPLE.is_file():
            return (
                EXIT_BAD_INPUT,
                {
                    "status": "error",
                    "message": f"{EXAMPLE} is missing from the plugin; reinstall the plugin",
                },
                None,
            )
        data_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(EXAMPLE, path)
        return (
            EXIT_CREATED,
            {
                "status": "created",
                "path": str(path),
                "message": (
                    "Created your registry from the example. Open it and fill in the Tracker, "
                    "Board, Lanes, Priority, Labels, Model labels and Repos for your team, then "
                    "run the command again."
                ),
            },
            None,
        )
    reg = parse(path.read_text(encoding="utf-8"))
    found = problems(reg)
    if found:
        return EXIT_INCOMPLETE, {"status": "incomplete", "path": str(path), "problems": found}, None
    return 0, {"status": "ok", "path": str(path)}, reg


def board_url(url: str, reg: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """Resolve a pasted board URL; the host must equal the registry's host."""
    patterns = (
        (r"^https?://([^/]+)/(?:users|orgs)/([^/]+)/projects/(\d+)(?:/.*)?$", "github-project"),
        (r"^https?://([^/]+)/groups/(.+?)/-/boards/(\d+)(?:[/?#].*)?$", "gitlab-group"),
        (r"^https?://([^/]+)/(.+?)/-/boards/(\d+)(?:[/?#].*)?$", "gitlab-project"),
    )
    for pattern, kind in patterns:
        match = re.match(pattern, url.strip())
        if not match:
            continue
        host, owner, number = match.groups()
        if reg["host"] and host.lower() != reg["host"].lower():
            return EXIT_HOST_MISMATCH, {
                "status": "host_mismatch",
                "message": f"the URL is on {host} but the registry's Host is {reg['host']}",
            }
        if kind == "github-project":
            return 0, {"kind": kind, "owner": owner, "number": int(number)}
        scope = Scope.GROUP if kind == "gitlab-group" else Scope.PROJECT
        return 0, {"kind": kind, "scope": scope, "path": owner, "board_id": int(number)}
    return EXIT_BAD_INPUT, {
        "status": "bad_url",
        "message": (
            f"'{url}' is not a recognized board URL. Expected "
            "https://github.com/(users|orgs)/<owner>/projects/<N>, "
            "https://<host>/groups/<path>/-/boards/<id> or https://<host>/<path>/-/boards/<id>"
        ),
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("ensure", "show", "board-url"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--data-dir", required=True, help="the plugin's data folder")
        if name == "board-url":
            cmd.add_argument("url")
    args = parser.parse_args(argv)
    data_dir = Path(args.data_dir).expanduser()

    code, payload, reg = ensure(data_dir)
    if reg is None:
        print(json.dumps(payload, indent=2))
        return code
    if args.command == "ensure":
        print(json.dumps(payload, indent=2))
        return 0
    if args.command == "show":
        print(json.dumps(to_json(reg), indent=2))
        return 0
    code, payload = board_url(args.url, reg)
    print(json.dumps(payload, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
