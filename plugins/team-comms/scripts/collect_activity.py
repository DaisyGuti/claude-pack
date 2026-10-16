#!/usr/bin/env python3
"""Collect a person's recent work from git and from GitHub (gh) or GitLab (glab) as JSON.

status-update reads this output and writes the standup or weekly update from it, so every
line of the update traces to a commit, pull request, merge request or issue.

Usage:
    collect_activity.py --since last-workday
    collect_activity.py --since week --repo ../api --repo ../web
    collect_activity.py --since 2026-10-06 --author me@example.com --host gitlab

--since accepts last-workday (the previous Monday to Friday day), week (the last 7 days),
Nd (the last N days) or YYYY-MM-DD. The window ends now.

A missing or signed-out gh/glab is not fatal: the repo's `warnings` list says what could
not be read and which command fixes it, and the git history is still reported.

Exit codes: 0 ok, 2 unusable input (not a git repository, no author, bad --since).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from shutil import which
from typing import Any

FIELD_SEP = "\x1f"
COMMAND_TIMEOUT_SECONDS = 30  # a forge call that takes longer than this is a stuck login or network
COMMIT_CAP = 2000  # newest commits read per repo; far above one person's work in a week
WARNING_DETAIL_MAX = 200  # enough for a CLI error sentence and the fix it names
LIST_LIMIT = 100  # per list call; a person rarely has more in one week, and the warning says if cut
LAST_WORKDAY_BACK = {5: 1, 6: 2, 0: 3}  # weekday() -> days back to Friday; other days: 1


class InputError(ValueError):
    """The caller passed something this script cannot use."""


def run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a command; a timeout comes back as a failed result, not an exception."""
    try:
        return subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        message = f"timed out after {COMMAND_TIMEOUT_SECONDS}s"
        return subprocess.CompletedProcess(cmd, 124, stdout="", stderr=message)


def resolve_start(spec: str, now: datetime) -> datetime:
    text = spec.strip().lower()
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if text == "last-workday":
        return midnight - timedelta(days=LAST_WORKDAY_BACK.get(now.weekday(), 1))
    if text == "week":
        return midnight - timedelta(days=7)
    days = re.fullmatch(r"(\d+)d", text)
    if days:
        return midnight - timedelta(days=int(days.group(1)))
    try:
        return datetime.combine(date.fromisoformat(spec.strip()), datetime.min.time()).astimezone()
    except ValueError as err:
        raise InputError(
            f"cannot read --since '{spec}'. Use last-workday, week, Nd or YYYY-MM-DD."
        ) from err


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def within(value: str | None, start: datetime) -> bool:
    stamp = parse_time(value)
    return stamp is not None and stamp >= start


def detect_host(remote_url: str) -> str:
    lowered = remote_url.lower()
    if "gitlab" in lowered:
        return "gitlab"
    if "github" in lowered:
        return "github"
    return "unknown"


def git_commits(repo: Path, author: str, start: datetime, end: datetime) -> list[dict[str, str]]:
    """List the author's commits on every branch whose author date falls in the window.

    The window is applied here and not with `git log --since`, because that flag stops
    walking at the first old commit it meets and so hides recent work after a rebase or
    cherry-pick put commits out of date order.
    """
    fmt = FIELD_SEP.join(["%h", "%aI", "%s"])
    result = run(
        [
            "git",
            "log",
            "--all",
            "--no-merges",
            "--fixed-strings",
            "-i",
            f"--author={author}",
            f"--max-count={COMMIT_CAP}",
            f"--format={fmt}",
        ],
        repo,
    )
    commits = []
    for line in result.stdout.splitlines():
        sha, when, subject = (line.split(FIELD_SEP) + ["", "", ""])[:3]
        stamp = parse_time(when)
        if stamp is not None and start <= stamp <= end:
            commits.append({"sha": sha, "date": when, "subject": subject})
    return commits


def git_state(repo: Path) -> dict[str, Any]:
    branch = run(["git", "branch", "--show-current"], repo).stdout.strip() or "(detached HEAD)"
    dirty = len(run(["git", "status", "--porcelain"], repo).stdout.splitlines())
    ahead = run(["git", "rev-list", "--count", "@{upstream}..HEAD"], repo)
    unpushed = int(ahead.stdout.strip()) if ahead.returncode == 0 else None
    return {"branch": branch, "uncommitted_files": dirty, "unpushed_commits": unpushed}


def failure_warning(cmd: list[str], result: subprocess.CompletedProcess[str]) -> str:
    """One readable line for a failed forge call; CLIs pad their errors with blank space."""
    detail = " ".join(result.stderr.split()) or "no output"
    if len(detail) > WARNING_DETAIL_MAX:
        detail = detail[:WARNING_DETAIL_MAX].rstrip() + "..."
    return f"`{' '.join(cmd[:3])}` failed: {detail}"


def load_json(result: subprocess.CompletedProcess[str]) -> Any:
    return json.loads(result.stdout) if result.stdout.strip() else []


def github_items(
    repo: Path, start: datetime, warnings: list[str]
) -> dict[str, list[dict[str, Any]]]:
    if run(["gh", "auth", "status"], repo).returncode != 0:
        warnings.append(
            "gh is not signed in; run `gh auth login`. Pull requests and issues skipped."
        )
        return {}
    pr_fields = "number,title,state,url,updatedAt,mergedAt,isDraft,reviewDecision,headRefName"
    queries = {
        "authored": [
            "gh",
            "pr",
            "list",
            "--author",
            "@me",
            "--state",
            "all",
            "--limit",
            str(LIST_LIMIT),
            "--json",
            pr_fields,
        ],
        "reviewed": [
            "gh",
            "pr",
            "list",
            "--search",
            "reviewed-by:@me -author:@me",
            "--state",
            "all",
            "--limit",
            str(LIST_LIMIT),
            "--json",
            "number,title,state,url,updatedAt",
        ],
        "review_requested": [
            "gh",
            "pr",
            "list",
            "--search",
            "review-requested:@me",
            "--state",
            "open",
            "--limit",
            str(LIST_LIMIT),
            "--json",
            "number,title,url,updatedAt",
        ],
        "issues": [
            "gh",
            "issue",
            "list",
            "--assignee",
            "@me",
            "--state",
            "all",
            "--limit",
            str(LIST_LIMIT),
            "--json",
            "number,title,state,url,updatedAt,closedAt",
        ],
    }
    out: dict[str, list[dict[str, Any]]] = {}
    for name, cmd in queries.items():
        result = run(cmd, repo)
        if result.returncode != 0:
            warnings.append(failure_warning(cmd, result))
            continue
        rows = load_json(result)
        if len(rows) >= LIST_LIMIT:
            warnings.append(
                f"{name}: hit the {LIST_LIMIT}-item cap, so older items may be missing."
            )
        kind = "issue" if name == "issues" else "pull_request"
        out[name] = [
            {
                "kind": kind,
                "number": row["number"],
                "title": row["title"],
                "state": str(row.get("state", "open")).lower(),
                "url": row["url"],
                "updated_at": row.get("updatedAt"),
                "merged_at": row.get("mergedAt"),
                "draft": row.get("isDraft"),
                "review_decision": row.get("reviewDecision"),
                "branch": row.get("headRefName"),
            }
            for row in rows
            if name == "review_requested" or within(row.get("updatedAt"), start)
        ]
    return out


def gitlab_items(
    repo: Path, start: datetime, warnings: list[str]
) -> dict[str, list[dict[str, Any]]]:
    user = run(["glab", "api", "user"], repo)
    if user.returncode != 0:
        warnings.append(
            "glab is not signed in; run `glab auth login`. Merge requests and issues skipped."
        )
        return {}
    username = json.loads(user.stdout)["username"]
    per_page = ["-P", str(LIST_LIMIT)]
    queries = {
        "authored": [
            "glab",
            "mr",
            "list",
            "--author",
            username,
            "--all",
            "-F",
            "json",
            "--order",
            "updated_at",
            *per_page,
        ],
        "review_requested": ["glab", "mr", "list", "--reviewer", username, "-F", "json", *per_page],
        "issues": [
            "glab",
            "issue",
            "list",
            "--assignee",
            username,
            "--all",
            "-O",
            "json",
            "--order",
            "updated_at",
            *per_page,
        ],
    }
    out: dict[str, list[dict[str, Any]]] = {}
    for name, cmd in queries.items():
        result = run(cmd, repo)
        if result.returncode != 0:
            warnings.append(failure_warning(cmd, result))
            continue
        rows = load_json(result)
        if len(rows) >= LIST_LIMIT:
            warnings.append(
                f"{name}: hit the {LIST_LIMIT}-item cap, so older items may be missing."
            )
        kind = "issue" if name == "issues" else "merge_request"
        out[name] = [
            {
                "kind": kind,
                "number": row["iid"],
                "title": row["title"],
                "state": {"opened": "open"}.get(row.get("state", ""), row.get("state")),
                "url": row["web_url"],
                "updated_at": row.get("updated_at"),
                "merged_at": row.get("merged_at"),
                "draft": row.get("draft"),
                "branch": row.get("source_branch"),
            }
            for row in rows
            if name == "review_requested" or within(row.get("updated_at"), start)
        ]
    warnings.append(
        "Reviews you completed on GitLab are not collected; ask the user if they matter."
    )
    return out


def collect_repo(
    path: Path, author: str | None, start: datetime, end: datetime, host_flag: str, use_forge: bool
) -> dict[str, Any]:
    inside = run(["git", "rev-parse", "--show-toplevel"], path)
    if inside.returncode != 0:
        raise InputError(f"{path} is not inside a git repository. Pass --repo with a repo path.")
    root = Path(inside.stdout.strip())
    email = author or run(["git", "config", "user.email"], root).stdout.strip()
    if not email:
        raise InputError(
            "no author to match. Pass --author EMAIL, or run "
            "`git config user.email you@example.com`."
        )
    remote = run(["git", "remote", "get-url", "origin"], root).stdout.strip()
    host = host_flag if host_flag != "auto" else detect_host(remote)
    warnings: list[str] = []
    forge: dict[str, list[dict[str, Any]]] = {}
    if not use_forge:
        warnings.append("Forge lookup skipped (--no-forge); only git history is reported.")
    elif host == "unknown":
        warnings.append("Remote is neither GitHub nor GitLab; pass --host github or --host gitlab.")
    else:
        cli = "gh" if host == "github" else "glab"
        if which(cli) is None:
            warnings.append(f"{cli} is not installed; install it to include {host} items.")
        else:
            forge = (github_items if host == "github" else gitlab_items)(root, start, warnings)
    return {
        "name": root.name,
        "host": host,
        "author": email,
        **git_state(root),
        "commits": git_commits(root, email, start, end),
        "authored": forge.get("authored", []),
        "reviewed": forge.get("reviewed", []),
        "review_requested": forge.get("review_requested", []),
        "issues": forge.get("issues", []),
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect recent work as JSON for status-update.")
    parser.add_argument("--since", default="last-workday")
    parser.add_argument("--repo", action="append", type=Path, help="repeatable; default is cwd")
    parser.add_argument("--author", help="git author email; default is git config user.email")
    parser.add_argument("--host", choices=["auto", "github", "gitlab"], default="auto")
    parser.add_argument("--no-forge", action="store_true", help="read git history only")
    args = parser.parse_args(argv)
    try:
        end = datetime.now().astimezone()
        start = resolve_start(args.since, end)
        repos = [
            collect_repo(path, args.author, start, end, args.host, not args.no_forge)
            for path in (args.repo or [Path.cwd()])
        ]
    except InputError as err:
        print(f"collect_activity.py: {err}", file=sys.stderr)
        return 2
    report = {
        "window": {
            "label": args.since,
            "since": start.isoformat(timespec="minutes"),
            "until": end.isoformat(timespec="minutes"),
        },
        "repos": repos,
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
