#!/usr/bin/env python3
"""Fetch and query the NIST SP 800-53 Rev 5 OSCAL catalog and its Low/Moderate/High baselines.

NIST publishes the controls and the three baselines as machine-readable OSCAL JSON. This
script downloads them once and answers three questions the security skills need: which
control IDs exist, what is the title of a control, and which controls a baseline includes.
Nothing is frozen in this repository, so a new NIST release is picked up by running `fetch`
again.

Usage:
    nist_catalog.py fetch --dest DIR
    nist_catalog.py show  --dir DIR  AC-2 "SC-7(5)" ...
    nist_catalog.py baseline --dir DIR  low|moderate|high  [--no-enhancements]
    nist_catalog.py ids   --dir DIR

Control IDs are written the way people write them (AC-2, SC-7(5)). The catalog stores them as
ac-2 and sc-7.5; this script converts both ways.

Exit codes: 0 success; 1 an ID was not found; 2 usage error, missing file or failed download.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

BASE_URL = (
    "https://raw.githubusercontent.com/usnistgov/oscal-content/main/nist.gov/SP800-53/rev5/json/"
)
CATALOG_FILE = "NIST_SP-800-53_rev5_catalog.json"
BASELINE_FILES = {
    level: f"NIST_SP-800-53_rev5_{level.upper()}-baseline_profile.json"
    for level in ("low", "moderate", "high")
}
# The catalog is about 10 MB; ninety seconds covers a slow connection without hanging forever.
DOWNLOAD_TIMEOUT_SECONDS = 90


def to_catalog_id(display: str) -> str:
    """AC-2 -> ac-2 and SC-7(5) -> sc-7.5."""
    text = display.strip().lower()
    if text.endswith(")") and "(" in text:
        base, _, enh = text.partition("(")
        return f"{base}.{enh.rstrip(')')}"
    return text


def to_display_id(catalog_id: str) -> str:
    """ac-2 -> AC-2 and sc-7.5 -> SC-7(5)."""
    base, _, enh = catalog_id.upper().partition(".")
    return f"{base}({enh})" if enh else base


def _walk(controls: list[dict[str, Any]], into: dict[str, str]) -> None:
    for control in controls:
        into[control["id"]] = control.get("title", "")
        _walk(control.get("controls", []), into)


def load_catalog_path(path: Path) -> dict[str, str]:
    """Return {catalog id: title} for every control and enhancement in a catalog file."""
    try:
        data = json.loads(path.read_text())
    except OSError as exc:
        raise FileNotFoundError(
            f"{path} not found. Run `nist_catalog.py fetch --dest <dir>` first."
        ) from exc
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{path} is not valid JSON ({exc}); delete it and run fetch again."
        ) from exc
    titles: dict[str, str] = {}
    for group in data["catalog"]["groups"]:
        _walk(group.get("controls", []), titles)
    return titles


def load_catalog(directory: Path) -> dict[str, str]:
    return load_catalog_path(directory / CATALOG_FILE)


def load_baseline(directory: Path, level: str) -> list[str]:
    """Return the catalog ids the baseline includes, in the profile's order."""
    path = directory / BASELINE_FILES[level]
    try:
        data = json.loads(path.read_text())
    except OSError as exc:
        raise FileNotFoundError(
            f"{path} not found. Run `nist_catalog.py fetch --dest {directory}` first."
        ) from exc
    ids: list[str] = []
    for imported in data["profile"]["imports"]:
        for include in imported.get("include-controls", []):
            ids.extend(include.get("with-ids", []))
    return ids


def catalog_version(directory: Path) -> str:
    data = json.loads((directory / CATALOG_FILE).read_text())
    meta = data["catalog"]["metadata"]
    return f"{meta.get('title', 'NIST SP 800-53 catalog')} (version {meta.get('version', '?')})"


def cmd_fetch(args: argparse.Namespace) -> int:
    dest = Path(args.dest).expanduser()
    dest.mkdir(parents=True, exist_ok=True)
    for name in [CATALOG_FILE, *BASELINE_FILES.values()]:
        url = BASE_URL + name
        try:
            with urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
                body = response.read()
            json.loads(body)  # refuse to keep a truncated or HTML error page
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            print(
                f"error: could not download {url}: {exc}. Check the network and retry.",
                file=sys.stderr,
            )
            return 2
        (dest / name).write_bytes(body)
        print(f"saved {dest / name}")
    print(f"catalog: {catalog_version(dest)}")
    print(f"source: {BASE_URL}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    titles = load_catalog(Path(args.dir))
    missing = 0
    for display in args.ids:
        title = titles.get(to_catalog_id(display))
        if title is None:
            print(f"{display}\tNOT FOUND in the catalog")
            missing += 1
        else:
            print(f"{to_display_id(to_catalog_id(display))}\t{title}")
    return 1 if missing else 0


def cmd_baseline(args: argparse.Namespace) -> int:
    directory = Path(args.dir)
    titles = load_catalog(directory)
    for catalog_id in load_baseline(directory, args.level):
        if args.no_enhancements and "." in catalog_id:
            continue
        print(f"{to_display_id(catalog_id)}\t{titles.get(catalog_id, '')}")
    return 0


def cmd_ids(args: argparse.Namespace) -> int:
    for catalog_id in load_catalog(Path(args.dir)):
        print(to_display_id(catalog_id))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    fetch = sub.add_parser("fetch", help="download the catalog and baselines")
    fetch.add_argument("--dest", required=True, help="directory to save the JSON files in")
    fetch.set_defaults(func=cmd_fetch)
    show = sub.add_parser("show", help="print the title of each control ID")
    show.add_argument("--dir", required=True)
    show.add_argument("ids", nargs="+")
    show.set_defaults(func=cmd_show)
    base = sub.add_parser("baseline", help="list the controls in a baseline")
    base.add_argument("--dir", required=True)
    base.add_argument("level", choices=sorted(BASELINE_FILES))
    base.add_argument("--no-enhancements", action="store_true")
    base.set_defaults(func=cmd_baseline)
    ids = sub.add_parser("ids", help="list every control and enhancement ID")
    ids.add_argument("--dir", required=True)
    ids.set_defaults(func=cmd_ids)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (FileNotFoundError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
