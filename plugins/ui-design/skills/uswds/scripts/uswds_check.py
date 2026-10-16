#!/usr/bin/env python3
"""Deterministic checks for a project that uses the U.S. Web Design System (USWDS).

Three subcommands. Each prints plain lines a person or Claude can act on.

    uswds_check.py version [--project DIR] [--latest X.Y.Z]
        Installed @uswds/uswds version against the latest on the npm registry.
    uswds_check.py classes --css FILE [--prefix REGEX ...] [--ignore REGEX ...] PATH...
        Class names in markup and templates that the compiled USWDS CSS does not define,
        such as a typo (usa-buton) or a class removed by an upgrade.
    uswds_check.py page PATH...
        Facts about each full HTML document: lang, title, viewport, meta description,
        skip link, official government banner, USWDS initializer and script.

Exit codes: 0 nothing to report, 1 findings (unknown classes, or a version that is behind),
2 the input could not be read or the registry could not be reached.

The script reports facts. Whether a missing banner or an old version matters depends on the
project's domain and contract, so the caller decides that. It reads string-literal class
attributes only; a class name assembled in code is not seen.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Iterable, Iterator
from pathlib import Path

NPM_LATEST_URL = "https://registry.npmjs.org/@uswds/uswds/latest"
# A registry answer arrives in well under a second; ten seconds only guards a hung network.
FETCH_TIMEOUT_SECONDS = 10
MIGRATION_URL = "https://designsystem.digital.gov/documentation/migration"

# File types that can carry a class attribute: plain HTML, JS frameworks and server templates.
TEMPLATE_SUFFIXES = {
    ".html",
    ".htm",
    ".jsx",
    ".tsx",
    ".js",
    ".ts",
    ".vue",
    ".svelte",
    ".astro",
    ".njk",
    ".twig",
    ".jinja",
    ".jinja2",
    ".j2",
    ".erb",
    ".ejs",
    ".hbs",
    ".liquid",
    ".php",
}
SKIPPED_DIRECTORIES = {"node_modules", ".git", "dist", "build", ".next", "coverage", "vendor"}

# Characters that mean a class token is built at run time (`{{ x }}`, `${x}`, `<%= x %>`).
DYNAMIC_TOKEN = re.compile(r"[{}$<>%@]")
CLASS_ATTRIBUTE = re.compile(
    r"""\bclass(?:Name)?\s*=\s*(?:"(?P<dq>[^"]*)"|'(?P<sq>[^']*)'|\{\s*`(?P<tpl>[^`]*)`\s*\})""",
    re.IGNORECASE,
)
CSS_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
CSS_CLASS = re.compile(r"\.((?:\\.|[A-Za-z0-9_-])+)")
CSS_ESCAPE = re.compile(r"\\(.)")
SEMVER = re.compile(r"^\s*v?(\d+)\.(\d+)\.(\d+)")


class CheckError(Exception):
    """An input problem that stops a subcommand; the message names the file and the fix."""


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as err:
        raise CheckError(
            f"cannot read {path}: {err.strerror}. Check the path and permissions."
        ) from err


def read_json(path: Path) -> dict[str, object]:
    try:
        data = json.loads(read_text(path))
    except json.JSONDecodeError as err:
        raise CheckError(
            f"{path} is not valid JSON (line {err.lineno}). Fix the file and re-run."
        ) from err
    if not isinstance(data, dict):
        raise CheckError(f"{path} should hold a JSON object at the top level.")
    return data


# --- version -----------------------------------------------------------------------------


def parse_semver(text: str) -> tuple[int, int, int] | None:
    match = SEMVER.match(text)
    return (int(match[1]), int(match[2]), int(match[3])) if match else None


def installed_version(project: Path) -> tuple[str, str] | None:
    """Return (version, where it was found) for @uswds/uswds, or None when it is not installed."""
    package = project / "node_modules/@uswds/uswds/package.json"
    if package.is_file():
        version = read_json(package).get("version")
        if isinstance(version, str):
            return version, "node_modules"
    lock = project / "package-lock.json"
    if lock.is_file():
        packages = read_json(lock).get("packages")
        entry = packages.get("node_modules/@uswds/uswds") if isinstance(packages, dict) else None
        if isinstance(entry, dict) and isinstance(entry.get("version"), str):
            return entry["version"], "package-lock.json"
    return None


def declared_spec(project: Path) -> str | None:
    manifest = project / "package.json"
    if not manifest.is_file():
        return None
    data = read_json(manifest)
    for section in ("dependencies", "devDependencies"):
        group = data.get(section)
        spec = group.get("@uswds/uswds") if isinstance(group, dict) else None
        if isinstance(spec, str):
            return spec
    return None


def fetch_latest() -> str:
    request = urllib.request.Request(NPM_LATEST_URL, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
            version = json.load(response).get("version")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as err:
        raise CheckError(
            f"could not read the latest @uswds/uswds version from {NPM_LATEST_URL}: {err}. "
            "Check the network, or pass --latest X.Y.Z from https://www.npmjs.com/package/@uswds/uswds."
        ) from err
    if not isinstance(version, str) or parse_semver(version) is None:
        raise CheckError(
            f"the npm registry answer from {NPM_LATEST_URL} carried no usable version."
        )
    return version


def run_version(args: argparse.Namespace) -> int:
    project = Path(args.project)
    if not project.is_dir():
        raise CheckError(
            f"--project {project} is not a directory. Pass the folder with package.json."
        )
    found = installed_version(project)
    spec = declared_spec(project)
    latest = args.latest or fetch_latest()
    latest_tuple = parse_semver(latest)
    if latest_tuple is None:
        raise CheckError(f"--latest {latest!r} is not a version like 3.14.0.")

    print(f"latest on npm: {latest}")
    if found is None:
        print("installed: not found (no node_modules/@uswds/uswds and no lockfile entry)")
        print(f"declared in package.json: {spec or 'not declared'}")
        print("next: install with `npm install @uswds/uswds --save-exact`, then re-run.")
        return 1
    version, where = found
    print(f"installed: {version} (from {where})")
    print(f"declared in package.json: {spec or 'not declared'}")
    if spec is not None and not re.fullmatch(r"\d+\.\d+\.\d+", spec.strip()):
        print(
            "note: package.json declares a range. USWDS documents `npm install --save-exact` "
            "so an update never changes the site without a decision."
        )
    installed_tuple = parse_semver(version)
    if installed_tuple is None:
        raise CheckError(f"installed version {version!r} is not a version like 3.14.0.")
    if installed_tuple >= latest_tuple:
        print("status: up to date")
        return 0
    if installed_tuple[0] < latest_tuple[0]:
        print(f"status: a major version behind. Read the migration guide first: {MIGRATION_URL}")
    else:
        print(
            "status: behind. Read the release notes before updating: "
            "https://github.com/uswds/uswds/releases"
        )
    return 1


# --- classes -----------------------------------------------------------------------------


def css_classes(css_path: Path) -> set[str]:
    """Every class selector in the compiled CSS, with escapes undone (tablet\\:x -> tablet:x)."""
    text = CSS_COMMENT.sub("", read_text(css_path))
    found = {CSS_ESCAPE.sub(r"\1", raw) for raw in CSS_CLASS.findall(text)}
    if not any(name.startswith("usa-") for name in found):
        raise CheckError(
            f"{css_path} defines no usa- classes. Point --css at the compiled USWDS stylesheet, "
            "for example node_modules/@uswds/uswds/dist/css/uswds.css."
        )
    return found


def iter_template_files(paths: Iterable[Path]) -> Iterator[Path]:
    for path in paths:
        if path.is_file():
            yield path
        elif path.is_dir():
            # Prune while walking: a project root holds node_modules, which can be huge.
            for root, folders, files in os.walk(path):
                folders[:] = sorted(f for f in folders if f not in SKIPPED_DIRECTORIES)
                for name in sorted(files):
                    if Path(name).suffix in TEMPLATE_SUFFIXES:
                        yield Path(root) / name
        else:
            raise CheckError(f"{path} does not exist. Pass a file or a folder of templates.")


def class_tokens(text: str) -> Iterator[tuple[int, str]]:
    """Yield (line number, class token) for every static token inside a class attribute."""
    for match in CLASS_ATTRIBUTE.finditer(text):
        value = match["dq"] or match["sq"] or match["tpl"] or ""
        line = text.count("\n", 0, match.start()) + 1
        for token in value.split():
            if not DYNAMIC_TOKEN.search(token):
                yield line, token


def run_classes(args: argparse.Namespace) -> int:
    known = css_classes(Path(args.css))
    prefixes = [re.compile(p) for p in (args.prefix or ["^usa-"])]
    ignores = [re.compile(p) for p in (args.ignore or [])]
    suggestion_pool = sorted(known)
    findings: list[dict[str, object]] = []
    checked_files = 0
    for path in iter_template_files(Path(p) for p in args.paths):
        checked_files += 1
        for line, token in class_tokens(read_text(path)):
            if token in known or not any(p.search(token) for p in prefixes):
                continue
            if any(i.search(token) for i in ignores):
                continue
            close = difflib.get_close_matches(token, suggestion_pool, n=1, cutoff=0.85)
            findings.append(
                {
                    "file": str(path),
                    "line": line,
                    "class": token,
                    "suggestion": close[0] if close else None,
                }
            )

    if args.json:
        print(json.dumps({"files_checked": checked_files, "unknown_classes": findings}, indent=2))
    else:
        for item in findings:
            hint = f' (did you mean "{item["suggestion"]}"?)' if item["suggestion"] else ""
            print(
                f'{item["file"]}:{item["line"]}: class "{item["class"]}" '
                f"is not defined in {args.css}{hint}"
            )
        print(f"checked {checked_files} file(s); {len(findings)} unknown class reference(s)")
        if findings:
            print(
                "note: a class added only by JavaScript at run time is not in the CSS either. "
                "Confirm each one, or skip it with --ignore REGEX."
            )
    return 1 if findings else 0


# --- page --------------------------------------------------------------------------------

HTML_ELEMENT = re.compile(r"<html\b([^>]*)>", re.IGNORECASE)
LANG_ATTRIBUTE = re.compile(r"""(?<![:\w-])lang\s*=\s*["']?([A-Za-z][A-Za-z-]*)""", re.IGNORECASE)
TITLE_ELEMENT = re.compile(r"<title\b[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
META_VIEWPORT = re.compile(r"""<meta\b[^>]*\bname\s*=\s*["']viewport["']""", re.IGNORECASE)
META_DESCRIPTION = re.compile(
    r"""<meta\b[^>]*\bname\s*=\s*["']description["'][^>]*>""", re.IGNORECASE
)
CONTENT_ATTRIBUTE = re.compile(r"""\bcontent\s*=\s*["']([^"']+)["']""", re.IGNORECASE)


def page_facts(text: str) -> dict[str, bool]:
    html_tag = HTML_ELEMENT.search(text)
    title = TITLE_ELEMENT.search(text)
    description = META_DESCRIPTION.search(text)
    return {
        "html lang attribute": bool(html_tag and LANG_ATTRIBUTE.search(html_tag.group(1))),
        "non-empty title": bool(title and title.group(1).strip()),
        "viewport meta": bool(META_VIEWPORT.search(text)),
        "meta description": bool(description and CONTENT_ATTRIBUTE.search(description.group(0))),
        "skip link (usa-skipnav)": bool(re.search(r"\busa-skipnav\b", text)),
        "official banner (usa-banner)": bool(re.search(r"\busa-banner\b", text)),
        "uswds-init script": bool(re.search(r"uswds-init(?:\.min)?\.js", text)),
        "uswds script": bool(re.search(r"uswds(?:\.min)?\.js", text.replace("uswds-init", ""))),
    }


def run_page(args: argparse.Namespace) -> int:
    results: list[dict[str, object]] = []
    for path in iter_template_files(Path(p) for p in args.paths):
        text = read_text(path)
        if not HTML_ELEMENT.search(text):
            results.append({"file": str(path), "document": False, "facts": {}})
            continue
        results.append({"file": str(path), "document": True, "facts": page_facts(text)})
    if args.json:
        print(json.dumps(results, indent=2))
        return 0
    for item in results:
        if not item["document"]:
            print(
                f"{item['file']}: no <html> element, so this is a partial. "
                "Run the check on the base layout."
            )
            continue
        print(item["file"])
        facts = item["facts"]
        assert isinstance(facts, dict)
        for name, present in facts.items():
            print(f"  {'present' if present else 'MISSING'}  {name}")
    return 0


# --- command line ------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    commands = parser.add_subparsers(dest="command", required=True)

    version = commands.add_parser("version", help="installed against latest @uswds/uswds")
    version.add_argument("--project", default=".", help="folder with package.json (default: .)")
    version.add_argument("--latest", help="use this version instead of asking the npm registry")
    version.set_defaults(run=run_version)

    classes = commands.add_parser(
        "classes", help="class names the compiled USWDS CSS does not define"
    )
    classes.add_argument("--css", required=True, help="compiled USWDS stylesheet (uswds.css)")
    classes.add_argument(
        "--prefix",
        action="append",
        help="regex for class names to check (default ^usa-; repeatable)",
    )
    classes.add_argument(
        "--ignore", action="append", help="regex for class names to skip (repeatable)"
    )
    classes.add_argument("--json", action="store_true", help="print JSON instead of lines")
    classes.add_argument("paths", nargs="+", help="template files or folders")
    classes.set_defaults(run=run_classes)

    page = commands.add_parser("page", help="facts about full HTML documents")
    page.add_argument("--json", action="store_true", help="print JSON instead of lines")
    page.add_argument("paths", nargs="+", help="HTML files or folders")
    page.set_defaults(run=run_page)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.run(args))
    except CheckError as err:
        print(f"error: {err}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
