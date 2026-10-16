#!/usr/bin/env python3
"""Print the facts about a git repository that a team CLAUDE.md needs, as JSON.

The project-setup skill runs this first, so every command and rule it writes down is read
from a file in the repo instead of guessed. It reads files and runs read-only git commands;
it never writes anything and never touches the network.

Usage:
    scan_repo.py [PATH]      PATH is any directory inside the repo (default: current directory)

Exit codes: 0 facts printed, 2 the path is missing or not inside a git repository.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any, NoReturn
from urllib.parse import urlparse

# Directories that hold third-party or generated code; walking them only adds noise.
SKIP_DIRS = {".git", "node_modules", "vendor", ".venv", "venv", "dist", "build", "__pycache__"}
# Dockerfiles deeper than this are almost always fixtures or vendored examples.
MAX_DEPTH = 4
# Enough history to tell the repo's commit habits apart from one odd commit.
COMMIT_SAMPLE = 30
CONVENTIONAL = re.compile(
    r"^(feat|fix|chore|docs|refactor|test|ci|build|perf|style|revert)(\([^)]+\))?!?:\s"
)
LOCKFILES = (
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "uv.lock",
    "poetry.lock",
    "Pipfile.lock",
    "go.sum",
    "Cargo.lock",
    "Gemfile.lock",
    "composer.lock",
)
INSTRUCTION_FILES = (
    "CLAUDE.md",
    "AGENTS.md",
    "CONTRIBUTING.md",
    "README.md",
    "SECURITY.md",
    ".pre-commit-config.yaml",
    "Makefile",
    "justfile",
)


def git(root: Path, *args: str) -> str | None:
    """Run a read-only git command in `root`; return stdout, or None when git says no."""
    proc = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, timeout=30, check=False
    )
    return proc.stdout.strip() if proc.returncode == 0 else None


def fail(message: str) -> NoReturn:
    """Print one actionable line to stderr and exit 2."""
    print(f"scan_repo.py: {message}", file=sys.stderr)
    sys.exit(2)


def find_root(path: Path) -> Path:
    """Return the top of the repository containing `path`, or exit 2."""
    if not path.is_dir():
        fail(f"{path} is not a directory; pass a directory inside the repo.")
    top = git(path, "rev-parse", "--show-toplevel")
    if not top:
        fail(f"{path} is not inside a git repository; pass the repo path as the first argument.")
    return Path(top)


def host_info(remote_url: str | None) -> dict[str, str | None]:
    """Classify the remote as github, gitlab or unknown from its hostname."""
    if not remote_url:
        return {"url": None, "host": None, "kind": "none"}
    if "://" in remote_url:
        host = urlparse(remote_url).hostname or ""
    else:  # scp-style: git@host:owner/repo.git
        match = re.match(r"^[^@]+@([^:]+):", remote_url)
        host = match.group(1) if match else ""
    lowered = host.lower()
    if lowered == "github.com" or lowered.startswith("github."):
        kind = "github"
    elif "gitlab" in lowered:
        kind = "gitlab"
    else:
        kind = "unknown"
    return {"url": remote_url, "host": host or None, "kind": kind}


def default_branch(root: Path) -> str | None:
    """The remote's default branch, falling back to a local main or master."""
    head = git(root, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if head:
        return head.removeprefix("origin/")
    for name in ("main", "master"):
        if git(root, "rev-parse", "--verify", "--quiet", f"refs/heads/{name}") is not None:
            return name
    return None


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def package_json_facts(root: Path) -> dict[str, Any] | None:
    path = root / "package.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(read_text(path))
    except json.JSONDecodeError as exc:
        return {"manifest": "package.json", "error": f"invalid JSON: {exc}"}
    scripts = data.get("scripts") if isinstance(data, dict) else None
    manager = "npm"
    if (root / "pnpm-lock.yaml").is_file():
        manager = "pnpm"
    elif (root / "yarn.lock").is_file():
        manager = "yarn"
    names = sorted(scripts) if isinstance(scripts, dict) else []
    return {"manifest": "package.json", "manager": manager, "scripts": names}


def makefile_targets(root: Path) -> list[str] | None:
    path = root / "Makefile"
    if not path.is_file():
        return None
    targets = re.findall(r"^([A-Za-z0-9_][A-Za-z0-9_.-]*)\s*:(?!=)", read_text(path), re.M)
    return sorted(set(targets))


def pyproject_facts(root: Path) -> dict[str, Any] | None:
    path = root / "pyproject.toml"
    if not path.is_file():
        return None
    try:
        data = tomllib.loads(read_text(path))
    except tomllib.TOMLDecodeError as exc:
        return {"manifest": "pyproject.toml", "error": f"invalid TOML: {exc}"}
    tool = data.get("tool", {})
    manager = "uv" if (root / "uv.lock").is_file() else None
    if (root / "poetry.lock").is_file() or "poetry" in tool:
        manager = "poetry"
    configured = sorted(t for t in ("pytest", "ruff", "mypy", "black", "pyright") if t in tool)
    return {"manifest": "pyproject.toml", "manager": manager, "tools_configured": configured}


def other_manifests(root: Path) -> list[str]:
    names = ("go.mod", "Cargo.toml", "pom.xml", "build.gradle", "build.gradle.kts", "Gemfile")
    return [n for n in names if (root / n).is_file()]


def ci_files(root: Path) -> list[str]:
    found = sorted(
        p.relative_to(root).as_posix() for p in (root / ".github/workflows").glob("*.y*ml")
    )
    if (root / ".gitlab-ci.yml").is_file():
        found.append(".gitlab-ci.yml")
    return found


def ci_commands(root: Path, files: list[str]) -> list[dict[str, str]]:
    """Single-line `run:` values (GitHub) and `script:` list items (GitLab), with their file."""
    found: list[dict[str, str]] = []
    for rel in files:
        in_script = False
        for line in read_text(root / rel).splitlines():
            stripped = line.strip()
            run = re.match(r"^-?\s*run:\s*(\S.*)$", stripped)
            if run and run.group(1) not in ("|", ">", "|-", ">-"):
                found.append({"file": rel, "command": run.group(1)})
                continue
            if re.match(r"^(before_|after_)?script:\s*$", stripped):
                in_script = True
                continue
            if in_script:
                item = re.match(r"^-\s+(.+)$", stripped)
                if item:
                    found.append({"file": rel, "command": item.group(1).strip("'\"")})
                elif stripped and not stripped.startswith("#"):
                    in_script = False
    return found


def walk_repo(root: Path) -> list[Path]:
    """Every file up to MAX_DEPTH levels down, skipping SKIP_DIRS."""
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        depth = len(Path(dirpath).relative_to(root).parts)
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and depth < MAX_DEPTH]
        files.extend(Path(dirpath) / name for name in filenames)
    return files


def dockerfile_facts(root: Path, files: list[Path]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for path in sorted(files):
        if not (path.name == "Dockerfile" or path.name.startswith("Dockerfile.")):
            continue
        stages: set[str] = set()
        images: list[dict[str, Any]] = []
        for line in read_text(path).splitlines():
            match = re.match(r"^\s*FROM\s+(?:--\S+\s+)*(\S+)(?:\s+AS\s+(\S+))?", line, re.I)
            if not match:
                continue
            image, alias = match.group(1), match.group(2)
            if image.lower() != "scratch" and image not in stages:
                images.append({"image": image, "digest_pinned": "@sha256:" in image})
            if alias:
                stages.add(alias)
        result.append({"path": path.relative_to(root).as_posix(), "from": images})
    return result


def action_pins(root: Path) -> dict[str, int]:
    """Count third-party GitHub Actions `uses:` references pinned to a full commit SHA."""
    pinned = unpinned = 0
    for path in (root / ".github/workflows").glob("*.y*ml"):
        for ref in re.findall(r"^\s*-?\s*uses:\s*([^\s#]+)", read_text(path), re.M):
            if ref.startswith(("./", "docker://")):
                continue
            if re.search(r"@[0-9a-f]{40}$", ref):
                pinned += 1
            else:
                unpinned += 1
    return {"pinned": pinned, "unpinned": unpinned}


def requirements_facts(files: list[Path], root: Path) -> list[dict[str, Any]]:
    result = []
    for path in sorted(files):
        if not re.match(r"^requirements.*\.txt$", path.name):
            continue
        lines = [
            ln.strip()
            for ln in read_text(path).splitlines()
            if ln.strip() and not ln.strip().startswith(("#", "-"))
        ]
        result.append(
            {
                "path": path.relative_to(root).as_posix(),
                "requirements": len(lines),
                "not_exactly_pinned": sum(1 for ln in lines if "==" not in ln),
            }
        )
    return result


def commit_facts(root: Path) -> dict[str, Any]:
    log = git(root, "log", f"-n{COMMIT_SAMPLE}", "--format=%G?%x09%s")
    rows = [r.split("\t", 1) for r in (log or "").splitlines() if "\t" in r]
    signed = sum(1 for status, _ in rows if status != "N")
    conventional = sum(1 for _, subject in rows if CONVENTIONAL.match(subject))
    return {
        "sampled": len(rows),
        "with_signature": signed,
        "conventional_commits": conventional,
        "gpgsign_config": git(root, "config", "--get", "commit.gpgsign"),
    }


def instruction_files(root: Path) -> dict[str, Any]:
    present = [n for n in INSTRUCTION_FILES if (root / n).is_file()]
    codeowners = [
        p
        for p in ("CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS", ".gitlab/CODEOWNERS")
        if (root / p).is_file()
    ]
    # Match on the names the directory really lists: on a case-insensitive filesystem a glob
    # for PULL_REQUEST_TEMPLATE.md also answers for pull_request_template.md and reports the
    # pattern's casing.
    review_templates = [
        p.relative_to(root).as_posix()
        for folder, wanted in (
            (root / ".github", lambda n: n.lower() == "pull_request_template.md"),
            (root / ".github/PULL_REQUEST_TEMPLATE", lambda n: n.endswith(".md")),
            (root / ".gitlab/merge_request_templates", lambda n: n.endswith(".md")),
        )
        if folder.is_dir()
        for p in folder.iterdir()
        if p.is_file() and wanted(p.name)
    ]
    return {
        "present": present,
        "codeowners": codeowners,
        "review_templates": sorted(review_templates),
    }


def scan(path: Path) -> dict[str, Any]:
    root = find_root(path)
    files = walk_repo(root)
    ci = ci_files(root)
    ecosystems = [f for f in (package_json_facts(root), pyproject_facts(root)) if f]
    return {
        "root": str(root),
        "remote": host_info(git(root, "remote", "get-url", "origin")),
        "default_branch": default_branch(root),
        "instruction_files": instruction_files(root),
        "ecosystems": ecosystems,
        "other_manifests": other_manifests(root),
        "makefile_targets": makefile_targets(root),
        "lockfiles": [n for n in LOCKFILES if (root / n).is_file()],
        "requirements_files": requirements_facts(files, root),
        "ci": {"files": ci, "commands": ci_commands(root, ci)},
        "dockerfiles": dockerfile_facts(root, files),
        "github_actions_pins": action_pins(root),
        "commits": commit_facts(root),
    }


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0
    if len(argv) > 2:
        print("scan_repo.py: takes at most one argument, the repo path.", file=sys.stderr)
        return 2
    target = Path(argv[1]) if len(argv) == 2 else Path.cwd()
    print(json.dumps(scan(target), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
