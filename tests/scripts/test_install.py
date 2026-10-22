"""Tests for install.sh against a stand-in `claude` command (no network, no real config)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
INSTALL = ROOT / "install.sh"
PLUGINS = [
    p["name"] for p in json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())["plugins"]
]

FAKE_CLAUDE = textwrap.dedent(
    """\
    #!/usr/bin/env python3
    # Stand-in for the claude command: keeps marketplaces and plugins in $FAKE_CLAUDE_STATE.
    import json, os, subprocess, sys
    state_file = os.environ["FAKE_CLAUDE_STATE"]
    state = json.load(open(state_file)) if os.path.exists(state_file) else {"m": {}, "p": {}}
    args = sys.argv[1:]
    def save():
        json.dump(state, open(state_file, "w"))
    def flag(name):
        return args[args.index(name) + 1] if name in args else "user"
    def version_of(plugin_id, record):
        # Like the real CLI: the commit prefix (12 chars) of the marketplace checkout, or empty
        # when that path is not a git repo. A test can pin a version to model a stale plugin.
        if "version" in record:
            return record["version"]
        path = state["m"].get(plugin_id.split("@", 1)[1], "")
        cmd = ["git", "-C", path, "rev-parse", "HEAD"]
        done = subprocess.run(cmd, capture_output=True, text=True)
        return done.stdout.strip()[:12] if path and done.returncode == 0 else ""
    if args == ["--version"]:
        print("2.1.300 (Claude Code)")
    elif args[:3] == ["plugin", "marketplace", "list"]:
        print(json.dumps([{"name": n, "source": "directory", "path": s, "installLocation": s}
                          for n, s in state["m"].items()]))
    elif args[:3] == ["plugin", "marketplace", "add"]:
        manifest = json.load(open(os.path.join(args[3], ".claude-plugin/marketplace.json")))
        state["m"][manifest["name"]] = args[3]
        save()
    elif args[:3] == ["plugin", "marketplace", "update"]:
        pass
    elif args[:3] == ["plugin", "marketplace", "remove"]:
        state["m"].pop(args[3], None)
        state["p"] = {k: v for k, v in state["p"].items() if not k.endswith("@" + args[3])}
        save()
    elif args[:2] == ["plugin", "list"]:
        print(json.dumps([{"id": k, "scope": v["scope"], "enabled": v["enabled"],
                           "version": version_of(k, v)}
                          for k, v in state["p"].items()]))
    elif args[:2] == ["plugin", "install"]:
        state["p"][args[2]] = {"scope": flag("--scope"), "enabled": True}
        save()
    elif args[:2] == ["plugin", "uninstall"]:
        state["p"].pop(args[2], None)
        save()
    else:
        sys.exit("fake claude: unexpected arguments " + " ".join(args))
    """
)


class Env:
    """A temporary config dir, a fake claude on PATH, and a way to run install.sh."""

    def __init__(self, tmp: Path) -> None:
        self.config = tmp / "config"
        self.config.mkdir()
        self.state = tmp / "state.json"
        bin_dir = tmp / "bin"
        bin_dir.mkdir()
        fake = bin_dir / "claude"
        fake.write_text(FAKE_CLAUDE)
        fake.chmod(0o755)
        # Stand-ins for the tracker CLIs, so a run never reaches the network or a real sign-in.
        for tool in ("gh", "glab"):
            stub = bin_dir / tool
            stub.write_text("#!/bin/sh\nexit 0\n")
            stub.chmod(0o755)
        self.env = {
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "CLAUDE_CONFIG_DIR": str(self.config),
            "FAKE_CLAUDE_STATE": str(self.state),
            # An empty git config, so the credential-helper check does not read the machine's.
            "GIT_CONFIG_GLOBAL": str(tmp / "gitconfig"),
            "GIT_CONFIG_NOSYSTEM": "1",
            # git refuses https and ssh, so reaching a remote fails at once instead of dialling out.
            "GIT_ALLOW_PROTOCOL": "file",
        }

    def run(self, *args: str) -> subprocess.CompletedProcess[str]:
        # The ROOT directory is also a valid local marketplace source: it holds marketplace.json.
        return subprocess.run(
            [str(INSTALL), "--source", str(ROOT), *args],
            capture_output=True,
            text=True,
            env=self.env,
            check=False,
        )

    def run_from_clone(
        self, tmp: Path, origin: str, *args: str, nested_in: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        """Run a copy of install.sh with no --source, from a git clone with this origin.

        With `nested_in`, the copy is unpacked inside a repository with that origin and is not a
        clone itself, like a zip download dropped into another project.
        """
        outer = nested_in or tmp / "clone"
        outer.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "-C", str(outer), "init", "-q"], check=True, env=self.env)
        subprocess.run(
            ["git", "-C", str(outer), "remote", "add", "origin", origin], check=True, env=self.env
        )
        pack = outer / "tools" / "pack" if nested_in else outer
        (pack / ".claude-plugin").mkdir(parents=True)
        shutil.copy(INSTALL, pack / "install.sh")
        shutil.copy(ROOT / ".claude-plugin/marketplace.json", pack / ".claude-plugin")
        return subprocess.run(
            [str(pack / "install.sh"), "--dry-run", "--only", "core", *args],
            capture_output=True,
            text=True,
            env=self.env,
            check=False,
        )

    def plugins(self) -> set[str]:
        if not self.state.exists():
            return set()
        return set(json.loads(self.state.read_text())["p"])

    def marketplaces(self) -> set[str]:
        if not self.state.exists():
            return set()
        return set(json.loads(self.state.read_text())["m"])


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return Env(tmp_path)


def test_install_adds_marketplace_and_every_plugin(env: Env) -> None:
    result = env.run()
    assert result.returncode == 0, result.stdout + result.stderr
    assert env.marketplaces() == {"claude-pack"}
    assert env.plugins() == {f"{name}@claude-pack" for name in PLUGINS}


def test_only_installs_the_named_plugins(env: Env) -> None:
    assert env.run("--only", "core,security").returncode == 0
    assert env.plugins() == {"core@claude-pack", "security@claude-pack"}


def test_unknown_plugin_name_stops_before_changing_anything(env: Env) -> None:
    result = env.run("--only", "core,nope")
    assert result.returncode == 1
    assert "no plugin named 'nope'" in result.stderr
    assert env.plugins() == set() and env.marketplaces() == set()


def test_dry_run_changes_nothing(env: Env) -> None:
    result = env.run("--dry-run")
    assert result.returncode == 0
    assert "would run: claude plugin install core@claude-pack" in result.stdout
    assert env.plugins() == set() and not (env.config / ".claude-pack-installed").exists()


def test_second_run_installs_nothing_new(env: Env) -> None:
    env.run()
    again = env.run()
    assert again.returncode == 0
    assert again.stdout.count("already installed:") == len(PLUGINS)
    assert "would run" not in again.stdout


def test_check_reports_missing_then_clean(env: Env) -> None:
    missing = env.run("--check")
    assert missing.returncode == 1
    assert "problem: marketplace claude-pack is not configured" in missing.stdout
    env.run()
    assert env.run("--check").returncode == 0


def test_check_flags_a_plugin_behind_the_marketplace_copy(env: Env, tmp_path: Path) -> None:
    # The version comparison only runs when the marketplace copy has a .git directory, which a
    # linked worktree does not (its .git is a file). Use a throwaway checkout of our own.
    source = tmp_path / "source"
    shutil.copytree(ROOT / ".claude-plugin", source / ".claude-plugin")
    git = ["git", "-C", str(source), "-c", "user.name=t", "-c", "user.email=t@example.com"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "init", "--no-gpg-sign"], check=True)

    def run_installer(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(INSTALL), "--source", str(source), *args],
            capture_output=True,
            text=True,
            env=env.env,
            check=False,
        )

    install = run_installer()
    assert install.returncode == 0, install.stdout + install.stderr
    assert run_installer("--check").returncode == 0
    data = json.loads(env.state.read_text())
    data["p"]["core@claude-pack"]["version"] = "000000000000"
    env.state.write_text(json.dumps(data))
    result = run_installer("--check")
    assert result.returncode == 1
    assert "core@claude-pack is at 000000000000 but the marketplace copy is at" in result.stdout
    assert "1 problem(s)" in result.stderr


def test_check_flags_a_disabled_plugin_and_changes_nothing(env: Env) -> None:
    env.run()
    data = json.loads(env.state.read_text())
    data["p"]["guardrails@claude-pack"]["enabled"] = False
    env.state.write_text(json.dumps(data))
    before = env.state.read_text()
    result = env.run("--check")
    assert result.returncode == 1
    assert "guardrails@claude-pack is installed but disabled" in result.stdout
    assert env.state.read_text() == before


def test_preferences_copied_only_when_none_exists(env: Env) -> None:
    target = env.config / "CLAUDE.md"
    assert env.run("--only", "core", "--with-preferences").returncode == 0
    assert target.read_text() == (ROOT / "preferences/CLAUDE.md").read_text()
    target.write_text("my own rules\n")
    result = env.run("--only", "core", "--with-preferences")
    assert "left alone" in result.stdout
    assert target.read_text() == "my own rules\n"


def test_existing_preferences_file_is_never_touched(env: Env) -> None:
    target = env.config / "CLAUDE.md"
    target.write_text("keep me\n")
    env.run("--only", "core", "--with-preferences")
    env.run("--uninstall")
    assert target.read_text() == "keep me\n"


def test_uninstall_removes_only_what_it_installed(env: Env) -> None:
    env.run("--only", "core")
    # A plugin the person installed on their own, from the same marketplace.
    subprocess.run(
        ["claude", "plugin", "install", "tickets@claude-pack", "--scope", "user"],
        env=env.env,
        check=True,
        capture_output=True,
    )
    result = env.run("--uninstall")
    assert result.returncode == 0
    assert env.plugins() == {"tickets@claude-pack"}
    assert "kept: marketplace claude-pack" in result.stdout
    assert env.marketplaces() == {"claude-pack"}


def test_uninstall_without_a_record_says_so(env: Env) -> None:
    result = env.run("--uninstall")
    assert result.returncode == 0
    assert "nothing to remove" in result.stdout


def test_other_source_for_the_same_marketplace_is_refused(env: Env, tmp_path: Path) -> None:
    env.run("--only", "core")
    other = tmp_path / "other"
    shutil.copytree(ROOT / ".claude-plugin", other / ".claude-plugin")
    result = subprocess.run(
        [str(INSTALL), "--source", str(other), "--only", "core"],
        capture_output=True,
        text=True,
        env=env.env,
        check=False,
    )
    assert result.returncode == 1
    assert "refused: marketplace 'claude-pack' is already configured" in result.stdout


# `.invalid` never resolves (RFC 2606), so no test reaches a real network host.
GITLAB_HOST = "gitlab.example.invalid"


def test_a_clone_from_gitlab_installs_from_that_gitlab(env: Env, tmp_path: Path) -> None:
    result = env.run_from_clone(tmp_path, f"https://{GITLAB_HOST}/group/claude-pack.git")
    assert f"adding marketplace claude-pack from https://{GITLAB_HOST}/group/claude-pack.git" in (
        result.stdout
    )
    assert "DaisyGuti/claude-pack" not in result.stdout


def test_a_token_in_the_clone_remote_never_reaches_claude(env: Env, tmp_path: Path) -> None:
    origin = f"https://oauth2:s3cr3t-token@{GITLAB_HOST}/group/claude-pack.git"
    result = env.run_from_clone(tmp_path, origin)
    assert f"from https://{GITLAB_HOST}/group/claude-pack.git" in result.stdout
    assert "s3cr3t-token" not in result.stdout + result.stderr


def test_an_ssh_clone_from_gitlab_is_used_as_written(env: Env, tmp_path: Path) -> None:
    result = env.run_from_clone(tmp_path, f"git@{GITLAB_HOST}:group/claude-pack.git")
    assert f"from git@{GITLAB_HOST}:group/claude-pack.git" in result.stdout
    assert "git has no credential helper" not in result.stdout  # SSH needs no helper
    assert f"load a key for {GITLAB_HOST} into ssh-agent" in result.stdout


def test_a_clone_from_github_keeps_the_github_name(env: Env, tmp_path: Path) -> None:
    result = env.run_from_clone(tmp_path, "git@github.com:Someone/claude-pack.git")
    assert "adding marketplace claude-pack from DaisyGuti/claude-pack" in result.stdout


def test_an_unreachable_gitlab_source_gets_glab_advice_not_gh(env: Env) -> None:
    result = subprocess.run(
        [
            str(INSTALL),
            "--dry-run",
            "--only",
            "core",
            "--source",
            f"https://{GITLAB_HOST}/group/claude-pack.git",
        ],
        capture_output=True,
        text=True,
        env=env.env,
        check=False,
    )
    assert f"glab auth login --hostname {GITLAB_HOST}" in result.stdout
    assert f"credential.https://{GITLAB_HOST}.helper '!glab auth git-credential'" in result.stdout
    assert "gh auth setup-git" not in result.stdout
    assert "not done: git has no credential helper for " + GITLAB_HOST in result.stdout


@pytest.mark.parametrize(
    "origin",
    [
        "https://User@GitHub.com/Someone/claude-pack.git",
        "ssh://git@ssh.github.com:443/Someone/claude-pack.git",
        "https://github.com/Someone/claude-pack",
    ],
)
def test_every_spelling_of_a_github_origin_keeps_the_github_name(
    env: Env, tmp_path: Path, origin: str
) -> None:
    result = env.run_from_clone(tmp_path, origin)
    assert "adding marketplace claude-pack from DaisyGuti/claude-pack" in result.stdout


def test_an_https_gitlab_origin_without_dot_git_is_read_as_a_git_url(
    env: Env, tmp_path: Path
) -> None:
    result = env.run_from_clone(tmp_path, f"https://{GITLAB_HOST}/group/claude-pack/")
    assert f"from https://{GITLAB_HOST}/group/claude-pack.git\n" in result.stdout


def test_a_pack_unpacked_inside_another_repository_ignores_that_repository(
    env: Env, tmp_path: Path
) -> None:
    outer_origin = f"https://{GITLAB_HOST}/team/infra.git"
    result = env.run_from_clone(tmp_path, outer_origin, nested_in=tmp_path / "infra")
    assert "adding marketplace claude-pack from DaisyGuti/claude-pack" in result.stdout
    assert "team/infra" not in result.stdout


def test_a_port_in_the_source_is_kept_for_the_credential_helper(env: Env) -> None:
    result = subprocess.run(
        [
            str(INSTALL),
            "--dry-run",
            "--only",
            "core",
            "--source",
            f"https://{GITLAB_HOST}:8443/group/claude-pack.git",
        ],
        capture_output=True,
        text=True,
        env=env.env,
        check=False,
    )
    assert f"credential.https://{GITLAB_HOST}:8443.helper" in result.stdout
    assert f"glab auth login --hostname {GITLAB_HOST}\n" in result.stdout


def test_glab_as_the_helper_for_the_source_host_is_recognized(env: Env, tmp_path: Path) -> None:
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text(
        f'[credential "https://{GITLAB_HOST}"]\n\thelper = !glab auth git-credential\n'
    )
    result = subprocess.run(
        [
            str(INSTALL),
            "--dry-run",
            "--only",
            "core",
            "--source",
            f"https://{GITLAB_HOST}/group/claude-pack.git",
        ],
        capture_output=True,
        text=True,
        env=env.env,
        check=False,
    )
    assert f"ok: git uses glab as its credential helper for {GITLAB_HOST}" in result.stdout
    # a GitHub-only helper does not count for a GitLab host
    gitconfig.write_text('[credential "https://github.com"]\n\thelper = !gh auth git-credential\n')
    result = subprocess.run(
        [str(INSTALL), "--dry-run", "--only", "core", "--source", f"https://{GITLAB_HOST}/g/r.git"],
        capture_output=True,
        text=True,
        env=env.env,
        check=False,
    )
    assert f"git has no credential helper for {GITLAB_HOST}" in result.stdout


def test_bad_scope_and_unknown_flag_fail(env: Env) -> None:
    assert env.run("--scope", "galaxy").returncode == 1
    assert env.run("--nonsense").returncode == 2


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="shellcheck is not installed")
def test_install_script_is_shellcheck_clean() -> None:
    result = subprocess.run(["shellcheck", "-x", str(INSTALL)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout
