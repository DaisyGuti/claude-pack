"""scan_repo.py reads facts from synthetic repos; nothing here touches the network."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "plugins/core/skills/project-setup/scripts"
SHA = "a" * 40


def test_reports_host_default_branch_and_commit_habits(scan_repo, make_repo):
    repo = make_repo(
        messages=("feat: add export", "fix(api): handle empty page", "update stuff"),
        remote="git@gitlab.example.invalid:team/app.git",
    )
    facts = scan_repo.scan(repo)
    assert facts["remote"]["kind"] == "gitlab"
    assert facts["remote"]["host"] == "gitlab.example.invalid"
    assert facts["default_branch"] == "main"
    assert facts["commits"]["sampled"] == 3
    assert facts["commits"]["conventional_commits"] == 2
    assert facts["commits"]["with_signature"] == 0


@pytest.mark.parametrize(
    ("url", "kind"),
    [
        ("https://github.com/org/app.git", "github"),
        ("git@github.com:org/app.git", "github"),
        ("https://git.corp.example.invalid/org/app.git", "unknown"),
        (None, "none"),
    ],
)
def test_host_kind(scan_repo, url, kind):
    assert scan_repo.host_info(url)["kind"] == kind


def test_reads_package_scripts_and_manager(scan_repo, make_repo):
    repo = make_repo(
        {
            "package.json": json.dumps({"scripts": {"test": "jest", "lint": "eslint ."}}),
            "pnpm-lock.yaml": "lockfileVersion: 9\n",
        }
    )
    facts = scan_repo.scan(repo)
    node = next(e for e in facts["ecosystems"] if e["manifest"] == "package.json")
    assert node["manager"] == "pnpm"
    assert node["scripts"] == ["lint", "test"]
    assert facts["lockfiles"] == ["pnpm-lock.yaml"]


def test_invalid_package_json_is_reported_not_raised(scan_repo, make_repo):
    repo = make_repo({"package.json": "{not json"})
    node = scan_repo.scan(repo)["ecosystems"][0]
    assert "invalid JSON" in node["error"]


def test_makefile_targets_skip_variables_and_special_targets(scan_repo, make_repo):
    repo = make_repo(
        {"Makefile": "CC := gcc\n.PHONY: test\ntest: build\n\tpytest\nbuild:\n\techo hi\n"}
    )
    assert scan_repo.scan(repo)["makefile_targets"] == ["build", "test"]


def test_pyproject_tools_and_uv_manager(scan_repo, make_repo):
    repo = make_repo(
        {
            "pyproject.toml": "[tool.ruff]\nline-length = 100\n[tool.pytest.ini_options]\n",
            "uv.lock": "version = 1\n",
        }
    )
    py = scan_repo.scan(repo)["ecosystems"][0]
    assert py["manager"] == "uv"
    assert py["tools_configured"] == ["pytest", "ruff"]


def test_ci_commands_from_github_and_gitlab(scan_repo, make_repo):
    repo = make_repo(
        {
            ".github/workflows/ci.yml": (
                "jobs:\n  t:\n    steps:\n      - run: npm test\n"
                "      - run: |\n          echo multi\n"
            ),
            ".gitlab-ci.yml": (
                "test:\n  script:\n    - make test\n    - make lint\n  only: [main]\n"
            ),
        }
    )
    commands = {c["command"] for c in scan_repo.scan(repo)["ci"]["commands"]}
    assert commands == {"npm test", "make test", "make lint"}


def test_dockerfile_digest_pinning_ignores_scratch_and_stage_names(scan_repo, make_repo):
    repo = make_repo(
        {
            "Dockerfile": (
                f"FROM golang:1.22@sha256:{'b' * 64} AS build\n"
                "FROM alpine:3.20\n"
                "FROM build AS final\n"
                "FROM scratch\n"
            )
        }
    )
    images = scan_repo.scan(repo)["dockerfiles"][0]["from"]
    assert images == [
        {"image": f"golang:1.22@sha256:{'b' * 64}", "digest_pinned": True},
        {"image": "alpine:3.20", "digest_pinned": False},
    ]


def test_github_actions_pin_counts_skip_local_and_docker_refs(scan_repo, make_repo):
    repo = make_repo(
        {
            ".github/workflows/ci.yml": (
                "steps:\n"
                f"  - uses: actions/checkout@{SHA}\n"
                "  - uses: actions/setup-node@v4\n"
                "  - uses: ./local-action\n"
                "  - uses: docker://alpine:3.20\n"
            )
        }
    )
    assert scan_repo.scan(repo)["github_actions_pins"] == {"pinned": 1, "unpinned": 1}


def test_requirements_not_exactly_pinned(scan_repo, make_repo):
    repo = make_repo({"requirements.txt": "# deps\nrequests==2.32.0\nflask>=3\n-r other.txt\n"})
    assert scan_repo.scan(repo)["requirements_files"] == [
        {"path": "requirements.txt", "requirements": 2, "not_exactly_pinned": 1}
    ]


def test_review_templates_and_codeowners(scan_repo, make_repo):
    repo = make_repo(
        {
            ".github/pull_request_template.md": "## What\n",
            ".gitlab/merge_request_templates/default.md": "## What\n",
            ".github/CODEOWNERS": "* @team\n",
            "SECURITY.md": "report here\n",
        }
    )
    files = scan_repo.scan(repo)["instruction_files"]
    assert files["review_templates"] == [
        ".github/pull_request_template.md",
        ".gitlab/merge_request_templates/default.md",
    ]
    assert files["codeowners"] == [".github/CODEOWNERS"]
    assert "SECURITY.md" in files["present"]


def test_node_modules_are_not_walked(scan_repo, make_repo):
    repo = make_repo({"node_modules/dep/Dockerfile": "FROM alpine\n"})
    assert scan_repo.scan(repo)["dockerfiles"] == []


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "scan_repo.py"), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_prints_json_for_a_repo(make_repo):
    repo = make_repo({"README.md": "hi\n"})
    result = run_cli(str(repo))
    assert result.returncode == 0
    assert json.loads(result.stdout)["root"] == str(repo.resolve())


def test_cli_outside_a_repo_exits_2_with_the_fix(tmp_path: Path):
    result = run_cli(str(tmp_path))
    assert result.returncode == 2
    assert "not inside a git repository" in result.stderr
    assert "pass the repo path" in result.stderr


def test_cli_missing_directory_exits_2(tmp_path: Path):
    result = run_cli(str(tmp_path / "nope"))
    assert result.returncode == 2
    assert "not a directory" in result.stderr


def test_cli_rejects_extra_arguments():
    result = run_cli("a", "b")
    assert result.returncode == 2
    assert "at most one argument" in result.stderr


def test_gpgsign_config_is_reported(scan_repo, make_repo):
    repo = make_repo()
    subprocess.run(
        ["git", "-C", str(repo), "config", "commit.gpgsign", "true"],
        check=True,
        capture_output=True,
    )
    assert scan_repo.scan(repo)["commits"]["gpgsign_config"] == "true"
