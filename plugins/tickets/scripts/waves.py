#!/usr/bin/env python3
"""Cut the ordered Ready units into waves that can run side by side.

`daily-grooming` step 8 hands this script the Ready lane in the step 5 order. A unit is a
loose ticket or a batch parent; a batch parent's plan holds a section per child, so the unit
carries every child's files. Each plan is read once for its **Files to touch**, and the waves
follow these rules, the same way on every run:

- flaky-test and CI units come first (a `flaky`, `flaky-test` or `ci` label, or a title about
  flakiness or a broken CI), and no other unit runs
  in a wave before the last one holding them;
- a unit that adds a migration, or whose files could not be read, gets a wave to itself;
- no two units in a wave share a file (a repo and a path; a folder holds every file in it);
- a wave holds at most `--pool` units (`work-tickets`' `--max-parallel`);
- a unit goes into the first wave with room that shares no file with it, so priority order
  holds within a wave.

Usage:
    waves.py UNITS_FILE --pool N

UNITS_FILE is JSON: {"units": [{"ref", "title", "repo", "labels": [...], "plan",
"children": [...]}]}, in the step 5 order. `plan` is the latest `### Final Plan` comment with any
`### Final Plan addendum` comments after it appended; its paths belong to `repo` unless one is
written in backticks as `` `other-repo: src/a.py` `` (`owner/other-repo` also works; a bare name
takes `repo`'s owner).
`labels` (a batch: every child's labels) and `children` default to empty. A ref listed twice,
or a child also listed as a unit, is bad input.

Prints JSON {"waves": [{"alone": reason or null, "units": [{"ref", "title", "children"}]}],
"no_files": [ref, ...]}. Exit codes: 0 printed, 2 bad input.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

if sys.version_info < (3, 11):  # noqa: UP036  (a clear message on an older python3)
    sys.exit("waves.py needs Python 3.11 or newer; install it and run this again")

# Labels and title phrases that mark a flaky-test or CI unit (orchestrator.md sorts the same way).
# A scoped label (`type:flaky-test`) counts by its last part. The title match is narrow on
# purpose: "Document the CI/CD pipeline" is not a CI fix.
FIRST_LABELS = frozenset({"flaky", "flaky-test", "ci"})
FIRST_TITLE = re.compile(
    r"\b(?:flaky|flakiness|intermittent(?:ly)?)\b"
    r"|\bci\s+(?:fail\w*|broken|red)\b"
    r"|\b(?:fix|unbreak)\s+(?:the\s+)?ci\b",
    re.IGNORECASE,
)
# A migration is a `migration` label or a file under a migrations folder (batches.md); grooming
# adds the label to a unit whose plan names a schema migration elsewhere.
MIGRATION_LABELS = frozenset({"migration"})
MIGRATION_DIRS = frozenset({"migrations", "migrate", "alembic"})
# The plan line that names the files (`**Files to touch**:` or `**Files to touch:**`), and the
# next bold section, numbered or bulleted, or heading that ends it.
FILES_HEADING = re.compile(r"\*\*Files to touch:?\*\*:?(.*)", re.IGNORECASE)
NEXT_SECTION = re.compile(r"^\s*(?:(?:[-*]|\d+\.)\s*)?\*\*[^*]+\*\*|^\s*#")
# A backticked span, or a bare path with at least one slash.
PATH = re.compile(r"`([^`\n]+)`|(?<![\w`/.-])((?:[\w.-]+/)+[\w.*-]*)")
# A backticked path another repo owns: `repo: path` or `owner/repo: path`.
QUALIFIED = re.compile(r"([\w-]+(?:/[\w.-]+)?):\s+(\S*(?:/|\.\w)\S*)")
# A backticked word is a file when it has a slash or a dot (`.env`, `a.py`) or starts with a capital
# (`Makefile`, `LICENSE`); `pytest` is not. A miss would let two workers share a file.
FILE_LIKE = re.compile(r"/|\.|^[A-Z]")
# A bare path that starts with a host name (`example.com/y`) is a URL fragment.
URL_HOST = re.compile(r"(?:[\w-]+\.)+(?:com|org|net|io|dev|gov|edu|mil|us)/", re.IGNORECASE)
# A line or symbol suffix on a path (`a.py:12-30`, `a.py::fn`) names the same file.
SUFFIX = re.compile(r"::.*$|:\d+(?:-\d+)?$")


class Alone(Enum):
    """Why a unit takes a wave of its own."""

    MIGRATION = "migration"
    NO_FILES = "no files read"


@dataclass(frozen=True)
class Unit:
    """One Ready unit as the waves see it, parsed once from its input entry."""

    ref: str
    title: str
    children: tuple[str, ...]
    files: frozenset[tuple[str, str]]
    first: bool
    alone: Alone | None


@dataclass
class Wave:
    alone: Alone | None = None
    units: list[Unit] = field(default_factory=list)
    files: set[tuple[str, str]] = field(default_factory=set)

    def takes(self, unit: Unit, pool: int) -> bool:
        return (
            self.alone is None
            and unit.alone is None
            and len(self.units) < pool
            and not any(overlaps(a, b) for a in self.files for b in unit.files)
        )

    def add(self, unit: Unit) -> None:
        self.units.append(unit)
        self.files |= unit.files


def overlaps(a: tuple[str, str], b: tuple[str, str]) -> bool:
    """Same repo, and the same path or one a folder holding the other (`src/` and `src/a.py`)."""
    (repo_a, path_a), (repo_b, path_b) = a, b
    if repo_a != repo_b:
        return False
    return path_a == path_b or path_b.startswith(path_a + "/") or path_a.startswith(path_b + "/")


def normalise(path: str) -> str:
    """One spelling per file: no `./`, no trailing slash or glob, no line or symbol suffix."""
    path = SUFFIX.sub("", path.removeprefix("./"))
    return path.split("*", 1)[0].rstrip("/")


def plan_paths(code: str | None, bare: str | None) -> list[tuple[str | None, str]]:
    """One PATH match as (repo it names or None, path) pairs; none when it is not a file.

    A backticked span with spaces is read word by word (`src/a.py: add a limit` names `src/a.py`).
    """
    if bare is not None:
        return [] if URL_HOST.match(bare) else [(None, bare)]
    span = (code or "").strip()
    if qualified := QUALIFIED.fullmatch(span):
        return [(qualified.group(1), qualified.group(2))]
    words = [w.rstrip(":,;") for w in span.split()]
    return [(None, w) for w in words if FILE_LIKE.search(w)]


def qualify(repo: str, named: str | None) -> str:
    """The unit's repo, or the one a path names (a bare name shares the unit repo's owner)."""
    if named is None:
        return repo.lower()
    owner = repo.rpartition("/")[0]
    return (named if "/" in named or not owner else f"{owner}/{named}").lower()


def files_to_touch(plan: str) -> list[tuple[str | None, str]]:
    """Every (repo or None, path) in each **Files to touch** section (one per batch child)."""
    section: list[str] = []
    reading = False
    for line in plan.splitlines():
        if match := FILES_HEADING.search(line):
            section.append(match.group(1))
            reading = True
        elif reading and not line.strip():
            # A blank line ends the section, unless the heading's list has not started yet.
            reading = not section[-1].strip()
        elif reading and NEXT_SECTION.match(line):
            reading = False
        elif reading:
            section.append(line)
    found = [
        p for a, b in PATH.findall("\n".join(section)) for p in plan_paths(a or None, b or None)
    ]
    paths = [(repo, normalise(path)) for repo, path in found]
    return [(repo, path) for repo, path in paths if path]


def string_list(entry: dict[str, object], key: str) -> list[str]:
    value = entry.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"unit {entry.get('ref')!r}: {key} must be a list")
    return [str(item) for item in value]


def parse_unit(entry: dict[str, object]) -> Unit:
    """Read one input entry into a Unit; a missing field raises ValueError."""
    missing = [k for k in ("ref", "title", "repo", "plan") if not isinstance(entry.get(k), str)]
    if missing:
        raise ValueError(f"unit {entry.get('ref')!r}: missing {', '.join(missing)}")
    title, repo, plan = str(entry["title"]), str(entry["repo"]), str(entry["plan"])
    labels = {label.lower().rpartition(":")[2] for label in string_list(entry, "labels")}
    paths = files_to_touch(plan)
    migration = bool(labels & MIGRATION_LABELS) or any(
        MIGRATION_DIRS.intersection(Path(p).parts) for _, p in paths
    )
    alone = Alone.MIGRATION if migration else None if paths else Alone.NO_FILES
    return Unit(
        ref=str(entry["ref"]),
        title=title,
        children=tuple(string_list(entry, "children")),
        files=frozenset((qualify(repo, named), p) for named, p in paths),
        first=bool(labels & FIRST_LABELS) or bool(FIRST_TITLE.search(title)),
        alone=alone,
    )


def cut_waves(units: list[Unit], pool: int) -> list[Wave]:
    """Place each unit in the first wave that takes it, flaky-test and CI ones first.

    The rest start at the last wave holding a flaky-test or CI unit, so none runs ahead of one.
    """
    waves: list[Wave] = []
    start = 0
    for group in ([u for u in units if u.first], [u for u in units if not u.first]):
        for unit in group:
            wave = next((w for w in waves[start:] if w.takes(unit, pool)), None)
            if wave is None:
                wave = Wave(alone=unit.alone)
                waves.append(wave)
            wave.add(unit)
        start = max(len(waves) - 1, 0)
    return waves


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("units_file", type=Path)
    parser.add_argument("--pool", type=int, required=True, help="work-tickets' --max-parallel")
    args = parser.parse_args(argv)
    if args.pool < 1:
        parser.error("--pool must be at least 1")
    try:
        data = json.loads(args.units_file.read_text(encoding="utf-8"))
        entries = data["units"] if isinstance(data, dict) else None
        if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
            raise ValueError('expected {"units": [ {...}, ... ]}')
        units = [parse_unit(entry) for entry in entries]
        refs = [u.ref for u in units] + [c for u in units for c in u.children]
        if repeated := sorted({r for r in refs if refs.count(r) > 1}):
            raise ValueError(f"listed more than once (a child is not its own unit): {repeated}")
    except (OSError, ValueError, KeyError) as exc:
        print(f"waves.py: {args.units_file}: {exc}", file=sys.stderr)
        return 2
    waves = cut_waves(units, args.pool)
    print(
        json.dumps(
            {
                "waves": [
                    {
                        "alone": wave.alone.value if wave.alone else None,
                        "units": [
                            {"ref": u.ref, "title": u.title, "children": list(u.children)}
                            for u in wave.units
                        ],
                    }
                    for wave in waves
                ],
                "no_files": [u.ref for u in units if u.alone is Alone.NO_FILES],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
