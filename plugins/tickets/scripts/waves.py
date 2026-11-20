#!/usr/bin/env python3
"""Cut the ordered Ready units into waves that can run side by side.

`daily-grooming` step 8 hands this script the Ready lane in the step 5 order. A unit is a
loose ticket or a batch parent; a batch parent's plan holds a section per child, so the unit
carries every child's files. Each plan is read once for its **Files to touch**, and the waves
follow these rules, the same way on every run:

- a flaky-test or CI unit comes first (its labels or title say so), in input order;
- a unit that adds a migration, or whose files could not be read, gets a wave to itself;
- no two units in a wave share a file (a file is a repo and a path);
- a wave holds at most `--pool` units (`work-tickets`' `--max-parallel`, 5 by default);
- a unit goes into the first wave with room that shares no file with it, so priority order
  holds within a wave.

Usage:
    waves.py UNITS_FILE [--pool N]

UNITS_FILE is JSON: {"units": [{"ref", "title", "repo", "labels": [...], "plan",
"children": [...]}]}, in the step 5 order. `plan` is the `### Final Plan` comment with any
`### Final Plan addendum` comments appended; `children` is empty for a loose ticket.

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

# work-tickets' --max-parallel default: a wave never holds more units than the pool runs.
DEFAULT_POOL = 5
# Labels and title words that mark a flaky-test or CI unit (orchestrator.md sorts the same way).
FIRST_LABELS = frozenset({"flaky", "flaky-test", "ci"})
FIRST_TITLE = re.compile(r"\b(flaky|ci)\b", re.IGNORECASE)
# A migration is a `migration` label or a file under a migrations folder (batches.md).
MIGRATION_LABELS = frozenset({"migration"})
MIGRATION_DIRS = frozenset({"migrations"})
# The plan line that names the files, and the next bold section that ends it.
FILES_HEADING = re.compile(r"\*\*Files to touch\*\*:?(.*)")
NEXT_SECTION = re.compile(r"^\s*(?:[-*]\s*)?\*\*[^*]+\*\*|^\s*#")
CODE_SPAN = re.compile(r"`([^`\s]+)`")


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
            and self.files.isdisjoint(unit.files)
        )

    def add(self, unit: Unit) -> None:
        self.units.append(unit)
        self.files |= unit.files


def files_to_touch(plan: str) -> list[str]:
    """Every code-span path in each **Files to touch** section (a batch plan has one per child)."""
    section: list[str] = []
    reading = False
    for line in plan.splitlines():
        if match := FILES_HEADING.search(line):
            section.append(match.group(1))
            reading = True
        elif reading and (not line.strip() or NEXT_SECTION.match(line)):
            reading = False
        elif reading:
            section.append(line)
    return CODE_SPAN.findall("\n".join(section))


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
    labels = {label.lower() for label in string_list(entry, "labels")}
    paths = [p.removeprefix("./") for p in files_to_touch(plan)]
    migration = bool(labels & MIGRATION_LABELS) or any(
        MIGRATION_DIRS.intersection(Path(p).parts[:-1]) for p in paths
    )
    alone = Alone.MIGRATION if migration else None if paths else Alone.NO_FILES
    return Unit(
        ref=str(entry["ref"]),
        title=title,
        children=tuple(string_list(entry, "children")),
        files=frozenset((repo, p) for p in paths),
        first=bool(labels & FIRST_LABELS) or bool(FIRST_TITLE.search(title)),
        alone=alone,
    )


def cut_waves(units: list[Unit], pool: int) -> list[Wave]:
    """Place each unit, flaky-test and CI ones first, in the first wave that takes it."""
    waves: list[Wave] = []
    # sorted() is stable, so input (priority) order holds inside each group.
    for unit in sorted(units, key=lambda u: not u.first):
        wave = next((w for w in waves if w.takes(unit, pool)), None)
        if wave is None:
            wave = Wave(alone=unit.alone)
            waves.append(wave)
        wave.add(unit)
    return waves


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("units_file", type=Path)
    parser.add_argument("--pool", type=int, default=DEFAULT_POOL)
    args = parser.parse_args(argv)
    if args.pool < 1:
        parser.error("--pool must be at least 1")
    try:
        data = json.loads(args.units_file.read_text(encoding="utf-8"))
        entries = data["units"] if isinstance(data, dict) else None
        if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
            raise ValueError('expected {"units": [ {...}, ... ]}')
        units = [parse_unit(entry) for entry in entries]
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
