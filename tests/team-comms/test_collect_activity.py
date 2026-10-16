"""Tests for scripts/collect_activity.py using a throwaway git repo and stub gh/glab programs."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "plugins/team-comms/scripts/collect_activity.py"
ME = "dev@example.com"


@pytest.fixture
def activity(load_script):
    return load_script("collect_activity")


def git(repo: Path, *args: str, when: datetime | None = None) -> None:
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
    if when:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = when.isoformat()
    subprocess.run(["git", *args], cwd=repo, env=env, check=True, capture_output=True)


def commit(repo: Path, name: str, author: str, when: datetime) -> None:
    (repo / name).write_text(name)
    git(repo, "add", name)
    git(
        repo,
        "-c", f"user.email={author}", "-c", "user.name=Dev",
        "commit", "-m", f"change {name}",
        when=when,
    )  # fmt: skip


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    path = tmp_path / "api"
    path.mkdir()
    git(path, "init", "-b", "main")
    git(path, "config", "user.email", ME)
    git(path, "config", "user.name", "Dev")
    git(path, "remote", "add", "origin", "https://github.com/acme/api.git")
    now = datetime.now().astimezone()
    commit(path, "recent.txt", ME, now - timedelta(days=1))
    commit(path, "old.txt", ME, now - timedelta(days=30))
    commit(path, "other.txt", "someone@example.com", now - timedelta(days=1))
    git(path, "checkout", "-b", "feature/x")
    commit(path, "branch.txt", ME, now - timedelta(hours=5))
    git(path, "checkout", "main")
    return path


def iso(days_ago: float) -> str:
    return (datetime.now().astimezone() - timedelta(days=days_ago)).isoformat()


def write_stub(directory: Path, name: str, body: str) -> None:
    stub = directory / name
    stub.write_text(f"#!{sys.executable}\nimport json, sys\nargs = sys.argv[1:]\n{body}\n")
    stub.chmod(0o755)


@pytest.fixture
def bin_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A PATH holding git and whichever stubs a test writes, and no real gh or glab."""
    path = tmp_path / "bin"
    path.mkdir()
    real_git = shutil.which("git")
    assert real_git
    (path / "git").symlink_to(real_git)
    monkeypatch.setenv("PATH", str(path))
    return path


def github_stub(directory: Path, signed_in: bool = True) -> None:
    data: dict[str, Any] = {
        "authored": [
            {"number": 7, "title": "Add retries", "state": "MERGED", "url": "https://gh/pr/7",
             "updatedAt": iso(1), "mergedAt": iso(1), "isDraft": False,
             "reviewDecision": "APPROVED", "headRefName": "feature/x"},
            {"number": 3, "title": "Old work", "state": "MERGED", "url": "https://gh/pr/3",
             "updatedAt": iso(40), "mergedAt": iso(40), "isDraft": False,
             "reviewDecision": "", "headRefName": "old"},
        ],
        "reviewed": [
            {"number": 9, "title": "Fix typo", "state": "MERGED", "url": "https://gh/pr/9",
             "updatedAt": iso(2)},
        ],
        "review_requested": [
            {"number": 12, "title": "Waiting", "url": "https://gh/pr/12", "updatedAt": iso(20)},
        ],
        "issues": [
            {"number": 21, "title": "Slow upload", "state": "OPEN", "url": "https://gh/i/21",
             "updatedAt": iso(1), "closedAt": None},
        ],
    }  # fmt: skip
    (directory / "gh_data.json").write_text(json.dumps(data))
    write_stub(
        directory,
        "gh",
        f"""
data = json.load(open({str(directory / "gh_data.json")!r}))
if args[:2] == ["auth", "status"]:
    sys.exit({0 if signed_in else 1})
if args[0] == "issue":
    print(json.dumps(data["issues"]))
elif "review-requested:@me" in args:
    print(json.dumps(data["review_requested"]))
elif any("reviewed-by:@me" in a for a in args):
    print(json.dumps(data["reviewed"]))
else:
    print(json.dumps(data["authored"]))
""",
    )


def gitlab_stub(directory: Path) -> None:
    data = {
        "mrs": [
            {"iid": 41, "title": "Add retries", "state": "merged", "web_url": "https://gl/mr/41",
             "updated_at": iso(1), "merged_at": iso(1), "draft": False, "source_branch": "f/x"},
            {"iid": 40, "title": "Old", "state": "merged", "web_url": "https://gl/mr/40",
             "updated_at": iso(50), "merged_at": iso(50), "draft": False, "source_branch": "old"},
        ],
        "reviewing": [
            {"iid": 44, "title": "Please review", "state": "opened", "web_url": "https://gl/mr/44",
             "updated_at": iso(9), "draft": False, "source_branch": "other"},
        ],
        "issues": [
            {"iid": 5, "title": "Flaky test", "state": "opened", "web_url": "https://gl/i/5",
             "updated_at": iso(0.5)},
        ],
    }  # fmt: skip
    (directory / "gl_data.json").write_text(json.dumps(data))
    write_stub(
        directory,
        "glab",
        f"""
data = json.load(open({str(directory / "gl_data.json")!r}))
if args[:2] == ["api", "user"]:
    print(json.dumps({{"username": "dev"}}))
elif args[0] == "issue":
    print(json.dumps(data["issues"]))
elif "--reviewer" in args:
    print(json.dumps(data["reviewing"]))
else:
    print(json.dumps(data["mrs"]))
""",
    )


def collect(activity, repo: Path, **kwargs: Any) -> dict[str, Any]:
    end = datetime.now().astimezone()
    options: dict[str, Any] = {
        "path": repo, "author": None, "start": end - timedelta(days=3), "end": end,
        "host_flag": "auto", "use_forge": True,
    }  # fmt: skip
    return activity.collect_repo(**{**options, **kwargs})


@pytest.mark.parametrize(
    ("spec", "now", "expected"),
    [
        ("last-workday", datetime(2026, 10, 14, 9, 0), datetime(2026, 10, 13)),
        ("last-workday", datetime(2026, 10, 12, 9, 0), datetime(2026, 10, 9)),
        ("last-workday", datetime(2026, 10, 18, 9, 0), datetime(2026, 10, 16)),
        ("week", datetime(2026, 10, 14, 9, 0), datetime(2026, 10, 7)),
        ("5d", datetime(2026, 10, 14, 9, 0), datetime(2026, 10, 9)),
    ],
)
def test_resolve_start(activity, spec: str, now: datetime, expected: datetime) -> None:
    assert activity.resolve_start(spec, now) == expected


def test_resolve_start_reads_a_date(activity) -> None:
    start = activity.resolve_start("2026-10-01", datetime(2026, 10, 14, 9, 0))
    assert (start.year, start.month, start.day, start.hour) == (2026, 10, 1, 0)


def test_resolve_start_refuses_junk(activity) -> None:
    with pytest.raises(activity.InputError, match="last-workday"):
        activity.resolve_start("lately", datetime(2026, 10, 14))


@pytest.mark.parametrize(
    ("url", "host"),
    [
        ("https://github.com/acme/api.git", "github"),
        ("git@gitlab.example.gov:team/api.git", "gitlab"),
        ("https://git.example.gov/team/api.git", "unknown"),
    ],
)
def test_detect_host(activity, url: str, host: str) -> None:
    assert activity.detect_host(url) == host


def test_git_history_filters_by_author_date_and_includes_other_branches(
    activity, repo: Path, bin_dir: Path
) -> None:
    result = collect(activity, repo, use_forge=False)
    subjects = sorted(c["subject"] for c in result["commits"])
    assert subjects == ["change branch.txt", "change recent.txt"]
    assert result["name"] == "api"
    assert result["branch"] == "main"


def test_git_state_counts_uncommitted_files(activity, repo: Path, bin_dir: Path) -> None:
    (repo / "wip.txt").write_text("x")
    result = collect(activity, repo, use_forge=False)
    assert result["uncommitted_files"] == 1
    assert result["unpushed_commits"] is None


def test_github_items_are_filtered_and_normalized(activity, repo: Path, bin_dir: Path) -> None:
    github_stub(bin_dir)
    result = collect(activity, repo)
    assert [pr["number"] for pr in result["authored"]] == [7]
    assert result["authored"][0]["state"] == "merged"
    assert result["authored"][0]["kind"] == "pull_request"
    assert [pr["number"] for pr in result["reviewed"]] == [9]
    # Waiting-on-me items stay even when they are older than the window.
    assert [pr["number"] for pr in result["review_requested"]] == [12]
    assert result["issues"][0]["kind"] == "issue"
    assert result["warnings"] == []


def test_github_signed_out_still_reports_git(activity, repo: Path, bin_dir: Path) -> None:
    github_stub(bin_dir, signed_in=False)
    result = collect(activity, repo)
    assert result["authored"] == []
    assert len(result["commits"]) == 2
    assert any("gh auth login" in w for w in result["warnings"])


def test_missing_cli_warns_with_the_fix(activity, repo: Path, bin_dir: Path) -> None:
    result = collect(activity, repo)
    assert any("gh is not installed" in w for w in result["warnings"])
    assert len(result["commits"]) == 2


def test_gitlab_items_are_normalized(activity, repo: Path, bin_dir: Path) -> None:
    gitlab_stub(bin_dir)
    git(repo, "remote", "set-url", "origin", "git@gitlab.example.gov:team/api.git")
    result = collect(activity, repo)
    assert result["host"] == "gitlab"
    assert [mr["number"] for mr in result["authored"]] == [41]
    assert result["authored"][0]["kind"] == "merge_request"
    assert result["review_requested"][0]["state"] == "open"
    assert result["issues"][0]["number"] == 5
    assert any("Reviews you completed on GitLab" in w for w in result["warnings"])


def test_host_flag_overrides_detection(activity, repo: Path, bin_dir: Path) -> None:
    gitlab_stub(bin_dir)
    result = collect(activity, repo, host_flag="gitlab")
    assert result["host"] == "gitlab"
    assert result["authored"]


def test_unknown_host_asks_for_the_flag(activity, repo: Path, bin_dir: Path) -> None:
    git(repo, "remote", "set-url", "origin", "https://git.example.gov/team/api.git")
    result = collect(activity, repo)
    assert any("--host" in w for w in result["warnings"])


def test_item_cap_is_reported(
    activity, repo: Path, bin_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    github_stub(bin_dir)
    monkeypatch.setattr(activity, "LIST_LIMIT", 1)
    result = collect(activity, repo)
    assert any("cap" in w for w in result["warnings"])


def test_timeout_becomes_a_failed_result(
    activity, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_a: Any, **_k: Any) -> None:
        raise subprocess.TimeoutExpired(cmd="gh", timeout=1)

    monkeypatch.setattr(activity.subprocess, "run", boom)
    result = activity.run(["gh", "pr", "list"], tmp_path)
    assert result.returncode == 124
    assert "timed out" in result.stderr


def run_cli(*args: str, cwd: Path, path: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PATH": path, "GIT_CONFIG_GLOBAL": os.devnull}
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], cwd=cwd, env=env, capture_output=True, text=True
    )


def test_cli_prints_the_report(repo: Path, bin_dir: Path) -> None:
    github_stub(bin_dir)
    result = run_cli("--since", "3d", "--repo", str(repo), cwd=repo.parent, path=str(bin_dir))
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["window"]["label"] == "3d"
    assert report["repos"][0]["authored"][0]["number"] == 7
    assert str(repo) not in result.stdout  # no machine paths in output that may reach Slack


def test_cli_outside_a_repo_exits_two(tmp_path: Path, bin_dir: Path) -> None:
    result = run_cli("--no-forge", cwd=tmp_path, path=str(bin_dir))
    assert result.returncode == 2
    assert "not inside a git repository" in result.stderr


def test_cli_without_an_author_exits_two(tmp_path: Path, bin_dir: Path) -> None:
    bare = tmp_path / "bare"
    bare.mkdir()
    git(bare, "init", "-b", "main")
    result = run_cli("--no-forge", cwd=bare, path=str(bin_dir))
    assert result.returncode == 2
    assert "git config user.email" in result.stderr


def test_cli_bad_since_exits_two(repo: Path, bin_dir: Path) -> None:
    result = run_cli("--since", "lately", cwd=repo, path=str(bin_dir))
    assert result.returncode == 2
    assert "YYYY-MM-DD" in result.stderr


def test_failure_warning_is_one_short_line(activity) -> None:
    noisy = subprocess.CompletedProcess(
        ["glab", "mr", "list"],
        1,
        stdout="",
        stderr="ERROR  \n          \n  no host.\n" + "x " * 400,
    )
    line = activity.failure_warning(["glab", "mr", "list", "--all"], noisy)
    assert "\n" not in line
    assert line.startswith("`glab mr list` failed: ERROR no host.")
    assert len(line) < 260
    assert line.endswith("...")
