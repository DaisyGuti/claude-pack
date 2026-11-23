#!/usr/bin/env python3
"""Measure what an agent loads into context before it starts work, and fail past a budget.

Agents read instruction files automatically: the root CLAUDE.md and every file it @-imports,
the root AGENTS.md, the user's memory index for the repo, and the AGENTS.md and CLAUDE.md of
each folder between the root and where the agent works. A guide that grows a little with every
merge request is never seen whole in a diff, but every agent pays for all of it on every run.

Usage:
    check_context_budget.py [ROOT] [--path FOLDER ...] [--all] [--json]

ROOT is the repo root (default: the current directory). Each --path is a folder inside ROOT; the
guides on the way from ROOT down to it are counted. --all counts every CLAUDE.md and AGENTS.md
in the repo instead, without the memory index and without the total limit (no agent loads
them all): the form a CI guard runs. Tokens are an estimate
(bytes / 4).

Limits: 40 KB per file and 60 KB in total, unless ROOT/.context-budget.toml says otherwise:

    guide_bytes = 40000
    total_bytes = 60000
    [baseline]               # a ratchet: a file already over the limit is held at its size
    "backend/AGENTS.md" = 395000

A baselined file may not grow past its baseline, and a baseline above its file's size is stale
(exit 1) until `--write-baseline` lowers it. The total limit rises by the excess the
baselines already hold. `--write-baseline` lowers or adds baseline entries for the files now
over the limit and never raises one.

Exit codes: 0 within budget, 1 over budget, 2 usage error (bad root, path or config).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path

CONFIG_NAME = ".context-budget.toml"
DEFAULT_GUIDE_BYTES = 40_000  # about 10k tokens: a guide this size is read whole on every run
DEFAULT_TOTAL_BYTES = 60_000  # about 15k tokens of instructions before any work starts
BYTES_PER_TOKEN = 4  # a rough average for English prose and code; an estimate, not a count
GUIDE_NAMES = ("CLAUDE.md", "AGENTS.md")
# Folders --all never enters: dependencies and VCS data hold other people's guides.
SKIP_DIRS = frozenset({".git", "node_modules", ".venv", "venv", "__pycache__"})
# `@path` outside a word, not inside a code span; whether it is an import is decided by the file
# existing, so `@types/node` or an e-mail address is left alone.
IMPORT = re.compile(r"(?<![\w`@])@([^\s`]+)")
CODE_SPAN = re.compile(r"`[^`\n]*`")
FENCE = re.compile(r"^\s*(```|~~~)")


class UsageError(Exception):
    """Bad root, path or config; main turns it into exit code 2."""


@dataclass(frozen=True)
class Limits:
    guide_bytes: int
    total_bytes: int
    baseline: dict[str, int]


@dataclass(frozen=True)
class Entry:
    path: Path
    label: str  # the key a baseline uses: the path from the root, or the absolute path outside it
    kind: str
    size: int


def load_limits(root: Path) -> Limits:
    config = root / CONFIG_NAME
    if not config.is_file():
        return Limits(DEFAULT_GUIDE_BYTES, DEFAULT_TOTAL_BYTES, {})
    try:
        data = tomllib.loads(config.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:  # ValueError: bad TOML or bytes that are not UTF-8
        raise UsageError(f"{config}: cannot read the config: {exc}") from exc
    values = {
        "guide_bytes": data.get("guide_bytes", DEFAULT_GUIDE_BYTES),
        "total_bytes": data.get("total_bytes", DEFAULT_TOTAL_BYTES),
    }
    baseline = data.get("baseline", {})
    ints = [*values.values(), *(baseline.values() if isinstance(baseline, dict) else [])]
    if not isinstance(baseline, dict) or any(
        isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in ints
    ):
        raise UsageError(
            f"{config}: guide_bytes and total_bytes must be whole numbers, and [baseline] a "
            'table of "path" = bytes'
        )
    return Limits(values["guide_bytes"], values["total_bytes"], baseline)


def imports_of(guide: Path) -> list[Path]:
    """Existing files a CLAUDE.md @-imports: relative to it, or the home folder after a tilde."""
    found: list[Path] = []
    fenced = False
    for line in guide.read_text(encoding="utf-8", errors="replace").splitlines():
        if FENCE.match(line):
            fenced = not fenced
        elif not fenced:
            for target in IMPORT.findall(CODE_SPAN.sub("", line)):
                try:
                    candidate = Path(target.rstrip(".,;:)")).expanduser()
                    resolved = candidate if candidate.is_absolute() else guide.parent / candidate
                    if resolved.is_file():
                        found.append(resolved.resolve())
                except (RuntimeError, OSError):
                    continue  # `@~nosuchuser/x` or a name too long for the file system: no import
    return found


def memory_index(root: Path) -> Path | None:
    """The memory index Claude Code keeps for a repo: the root's path with every
    non-alphanumeric character turned into a hyphen names the project folder."""
    config_dir = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    slug = re.sub(r"[^A-Za-z0-9]", "-", str(root))
    index = config_dir / "projects" / slug / "memory" / "MEMORY.md"
    return index if index.is_file() else None


def resolve_folder(root: Path, folder: str) -> Path:
    path = (root / folder).resolve()
    if path != root and root not in path.parents:
        raise UsageError(f"--path {folder}: not inside the repo root {root}; give a folder in it")
    if not path.is_dir():
        raise UsageError(f"--path {folder}: no such folder in {root}; check the spelling")
    return path


def guide_folders(root: Path) -> list[Path]:
    """Every folder of the repo, root first, that may hold a guide: the folders of its tracked
    and unignored guide files in a git repo (fast, skips ignored dependencies), a walk otherwise."""
    git = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"]
        + [f"*{name}" for name in GUIDE_NAMES],
        capture_output=True,
        check=False,
    )
    if git.returncode == 0 and (root / ".git").exists():
        found = {(root / rel).parent for rel in git.stdout.decode().split("\0") if rel}
    else:
        found = set()
        for here, dirs, _ in os.walk(root):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            found.add(Path(here))
    return sorted({root, *found}, key=lambda p: p.relative_to(root).parts)


def collect(root: Path, folders: list[Path], everything: bool = False) -> list[Entry]:
    """Every file loaded automatically, each once, in load order."""
    seen: set[Path] = set()
    entries: list[Entry] = []

    def add(path: Path, kind: str) -> bool:
        path = path.resolve()
        if path in seen or not path.is_file():
            return False
        seen.add(path)
        label = path.relative_to(root).as_posix() if root in path.parents else str(path)
        entries.append(Entry(path, label, kind, path.stat().st_size))
        return True

    def follow_imports(guide: Path) -> None:
        for target in imports_of(guide):
            if add(target, "import"):  # a file already seen is never read again: cycle-safe
                follow_imports(target)

    def visit(folder: Path) -> None:
        for name in GUIDE_NAMES:
            if add(folder / name, "nested") and name == "CLAUDE.md":
                follow_imports(folder / name)

    if add(root / "CLAUDE.md", "claude"):
        follow_imports(root / "CLAUDE.md")
    add(root / "AGENTS.md", "agents")
    if everything:
        for here in guide_folders(root):
            visit(here)
        return entries
    if index := memory_index(root):
        add(index, "memory")
    for folder in folders:
        here = root
        for part in folder.relative_to(root).parts:
            here = here / part
            visit(here)
    return entries


def tokens(size: int) -> int:
    return -(-size // BYTES_PER_TOKEN)


def evaluate(entries: list[Entry], limits: Limits, check_total: bool = True) -> dict[str, object]:
    """Measure the entries against the limits; the JSON report main prints."""
    over = []
    for entry in entries:
        cap = limits.baseline.get(entry.label, limits.guide_bytes)
        if entry.size > cap:
            over.append(
                {
                    "path": entry.label,
                    "bytes": entry.size,
                    "limit": cap,
                    "over_by": entry.size - cap,
                    "baselined": entry.label in limits.baseline,
                }
            )
    # A baselined file over the guide limit is held where it is, so its excess is not new growth.
    held = sum(
        max(0, min(e.size, limits.baseline[e.label]) - limits.guide_bytes)
        for e in entries
        if e.label in limits.baseline
    )
    # A baseline that sits above its file's size has not been lowered yet; failing here keeps a
    # shrunk file from growing back to its old size under a stale entry.
    stale = [
        {"path": e.label, "bytes": e.size, "baseline": limits.baseline[e.label]}
        for e in entries
        if e.label in limits.baseline and e.size < limits.baseline[e.label]
    ]
    total = sum(e.size for e in entries)
    total_over = max(0, total - limits.total_bytes - held) if check_total else 0
    return {
        "limits": {
            "guide_bytes": limits.guide_bytes,
            "total_bytes": limits.total_bytes,
            "held_by_baseline_bytes": held,
        },
        "token_estimate": f"bytes / {BYTES_PER_TOKEN}, an estimate",
        "files": [
            {"path": e.label, "kind": e.kind, "bytes": e.size, "tokens_est": tokens(e.size)}
            for e in entries
        ],
        "total_bytes": total,
        "total_tokens_est": tokens(total),
        "large": [e.label for e in entries if e.size > limits.guide_bytes],
        "over_budget": over,
        "stale_baseline": stale,
        "total_over_by": total_over,
        "ok": not over and not stale and not total_over,
    }


def safe_label(label: str) -> bool:
    """A baseline key is a path inside the repo: relative, with no `..`."""
    path = Path(label)
    return not path.is_absolute() and ".." not in path.parts


def write_baseline(root: Path, entries: list[Entry], limits: Limits) -> None:
    """Hold each file now over the limit at its size; lower an entry, never raise one.

    An entry for a guide this run did not measure (it is still on disk) stays as it was.
    """
    config = root / CONFIG_NAME
    if config.is_symlink() or (config.exists() and root not in config.resolve().parents):
        raise UsageError(f"{config}: is a symlink or leaves the repo; replace it with a plain file")
    measured = {e.label for e in entries}
    new = {
        label: size
        for label, size in limits.baseline.items()
        if label not in measured and safe_label(label) and (root / label).is_file()
    }
    for e in entries:
        # A file outside the repo (an import, the memory index) is machine-specific: never held.
        if e.size > limits.guide_bytes and safe_label(e.label):
            new[e.label] = min(e.size, limits.baseline.get(e.label, e.size))
    lines = [f"guide_bytes = {limits.guide_bytes}", f"total_bytes = {limits.total_bytes}"]
    if new:
        lines += ["", "[baseline]", *(f"{json.dumps(k)} = {v}" for k, v in sorted(new.items()))]
    # Write beside the target and swap it in, so a half-written file never replaces the config.
    fd, temp = tempfile.mkstemp(dir=root, prefix=CONFIG_NAME + ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
        os.replace(temp, config)
    except BaseException:
        os.unlink(temp)
        raise


def render(report: dict[str, object]) -> str:
    files = report["files"]
    assert isinstance(files, list)
    out = ["Auto-loaded context (tokens are an estimate: bytes / 4)"]
    out += [
        f"  {f['bytes']:>9,} B  ~{f['tokens_est']:>7,} tok  {f['kind']:<7} {f['path']}"
        for f in files
    ]
    if not files:
        out.append("  (no instruction files found)")
    out.append(f"  {report['total_bytes']:>9,} B  ~{report['total_tokens_est']:>7,} tok  total")
    limits = report["limits"]
    assert isinstance(limits, dict)
    out.append(
        f"Limits: {limits['guide_bytes']:,} B per file, {limits['total_bytes']:,} B in total"
        + (
            f" (+{limits['held_by_baseline_bytes']:,} held by the baseline)"
            if limits["held_by_baseline_bytes"]
            else ""
        )
    )
    over = report["over_budget"]
    assert isinstance(over, list)
    for item in over:
        kind = "baseline" if item["baselined"] else "limit"
        out.append(
            f"OVER {item['path']}: {item['bytes']:,} B, {item['over_by']:,} B past its {kind} "
            f"of {item['limit']:,} B. Split it: move area detail into a guide the index links to."
        )
    if report["total_over_by"]:
        out.append(f"OVER total: {report['total_over_by']:,} B past the total limit.")
    stale = report["stale_baseline"]
    assert isinstance(stale, list)
    out += [
        f"STALE {item['path']}: {item['bytes']:,} B, baseline {item['baseline']:,} B. "
        "Lower it with --write-baseline."
        for item in stale
    ]
    out.append("Within budget." if report["ok"] else "Over budget.")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("root", nargs="?", default=".", help="the repo root (default: .)")
    parser.add_argument(
        "--path",
        action="append",
        default=[],
        metavar="FOLDER",
        help="a folder in the repo the agent works in (repeatable)",
    )
    parser.add_argument(
        "--all", action="store_true", help="count every CLAUDE.md and AGENTS.md in the repo"
    )
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help=f"lower or add {CONFIG_NAME} baseline entries for files over the limit (never raises)",
    )
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:  # argparse exits 2 on a usage error already
        return int(exc.code or 0)
    try:
        root = Path(args.root).resolve()
        if not root.is_dir():
            raise UsageError(f"{args.root}: not a folder; give the repo root")
        limits = load_limits(root)
        entries = collect(root, [resolve_folder(root, f) for f in args.path], args.all)
        if args.write_baseline:
            write_baseline(root, entries, limits)
            limits = load_limits(root)
    except (UsageError, OSError) as exc:
        print(f"check_context_budget.py: {exc}", file=sys.stderr)
        return 2
    report = evaluate(entries, limits, check_total=not args.all)
    print(json.dumps(report, indent=2) if args.json else render(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
