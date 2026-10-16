"""Tests for render_cutover_checklist.py. Synthetic inventories only; no network."""

from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "plugins/secure-build/skills/gitlab-migration/scripts"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


inventory = _load("gitlab_migration_inventory_for_checklist", "inventory_github_repo.py")
checklist = _load("gitlab_migration_checklist", "render_cutover_checklist.py")


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


DEPLOY_WORKFLOW = """\
on:
  push:
    branches: [main]
jobs:
  deploy:
    runs-on: [self-hosted, gpu]
    environment: production
    permissions:
      id-token: write
    steps:
      - uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: projects/1/locations/global/pools/p/providers/g
      - run: echo ${{ secrets.DEPLOY_KEY }} ${{ vars.REGION }} ${{ secrets.GITHUB_TOKEN }}
"""


@pytest.fixture
def full_inventory(tmp_path: Path) -> dict:
    root = tmp_path / "proj"
    _write(root, ".github/workflows/deploy.yml", DEPLOY_WORKFLOW)
    _write(root, ".github/workflows/bad.yml", "on: push\nx: &a 1\n")
    _write(root, ".github/CODEOWNERS", "* @acme/platform # all\n")
    _write(
        root,
        ".github/dependabot.yml",
        "version: 2\nupdates:\n  - package-ecosystem: npm\n    directory: /\n"
        "    schedule:\n      interval: weekly\n  - package-ecosystem: pip\n    directory: /\n"
        "    schedule:\n      interval: daily\n",
    )
    _write(root, ".gitattributes", "*.bin filter=lfs\n")
    _write(root, ".gitmodules", '[submodule "a"]\n\tpath = a\n\turl = ../a.git\n')
    _write(root, "README.md", "https://github.com/acme/proj\n")
    _write(root, ".git/config", '[remote "origin"]\n\turl = git@github.com:acme/proj.git\n')
    return inventory.build_inventory(root)


@pytest.fixture
def bare_inventory(tmp_path: Path) -> dict:
    root = tmp_path / "bare"
    root.mkdir()
    return inventory.build_inventory(root)


def _render(inv: dict, **kw) -> str:
    args = {
        "gitlab_host": "gitlab.com",
        "gitlab_path": "grp/proj",
        "github_repo": "acme/proj",
        "tier": "unknown",
    }
    args.update(kw)
    return checklist.render(inv, **args)


def test_every_task_is_a_checkbox_and_sections_present(full_inventory):
    text = _render(full_inventory)
    for heading in (
        "## 0. Decisions before anything runs",
        "## 4. Pipelines",
        "## 5. Secrets and variables",
        "## 9. Mirror period",
        "## 11. Cutover day",
        "## 12. Rollback",
        "## 13. After cutover",
    ):
        assert heading in text
    task_lines = [ln for ln in text.splitlines() if ln.lstrip().startswith("- [")]
    assert task_lines and all(ln.lstrip().startswith("- [ ]") for ln in task_lines)


def test_one_task_per_workflow_and_secret(full_inventory):
    text = _render(full_inventory)
    assert "Translate `.github/workflows/deploy.yml`" in text
    assert "Translate `.github/workflows/bad.yml`" in text
    assert "Could not be parsed" in text
    assert "`DEPLOY_KEY`" in text
    assert "`REGION`" in text
    assert "GITHUB_TOKEN" in text and "CI_JOB_TOKEN" in text
    assert "`production`" in text
    assert "`gpu`" in text and "`self-hosted`" in text


def test_wif_section_present_only_when_used(full_inventory, bare_inventory):
    assert "## 6. Google Cloud trust" in _render(full_inventory)
    assert "## 6. Google Cloud trust" not in _render(bare_inventory)


def test_codeowners_tasks(full_inventory):
    text = _render(full_inventory)
    assert "Move the file from `.github/CODEOWNERS`" in text
    assert "`@acme/platform`" in text
    assert "inline comments" in text


def test_dependabot_mapping_lists_ecosystems(full_inventory):
    text = _render(full_inventory)
    assert "`npm` (weekly): Renovate manager npm" in text
    assert "`pip` (daily)" in text
    assert "templates/renovate.json" in text


def test_lfs_and_submodule_tasks(full_inventory):
    text = _render(full_inventory)
    assert "git lfs pull" in text
    assert "relative URL" in text


def test_bare_inventory_still_renders(bare_inventory):
    text = _render(bare_inventory)
    assert "No workflow files were found" in text
    assert "No `secrets.*` names found" in text
    assert "None found in the checkout." in text
    assert "CODEOWNERS" not in text.split("## 8.")[0].split("## 7.")[1]


@pytest.mark.parametrize(
    ("tier", "expect_tag", "expect_fragment"),
    [
        ("free", True, "tier is free"),
        ("premium", False, ""),
        ("ultimate", False, ""),
        ("unknown", True, "confirm the tier"),
    ],
)
def test_tier_tags(full_inventory, tier, expect_tag, expect_fragment):
    text = _render(full_inventory, tier=tier)
    push_rules = next(ln for ln in text.splitlines() if ln.startswith("- [ ] Push rules"))
    assert ("[needs Premium" in push_rules) is expect_tag
    if expect_tag:
        assert expect_fragment in push_rules


def test_pull_mirror_tagged_free(full_inventory):
    text = _render(full_inventory, tier="free")
    line = next(ln for ln in text.splitlines() if "GitHub as the source of truth" in ln)
    assert "needs Premium" in line


def test_self_managed_adds_instance_notes(full_inventory):
    text = _render(full_inventory, gitlab_host="git.example.org")
    assert "self-managed" in text
    assert "https://git.example.org/help" in text
    assert "https://git.example.org/.well-known/openid-configuration" in text
    assert "https://git.example.org/help" not in _render(full_inventory)


def test_no_secret_values_leak(full_inventory):
    text = _render(full_inventory)
    assert "projects/1/locations" not in text
    assert "echo" not in text


# -------------------------------------------------------------------------------- CLI


def _inventory_file(tmp_path: Path, inv: dict) -> Path:
    path = tmp_path / "inv.json"
    path.write_text(json.dumps(inv))
    return path


def test_cli_reads_file_and_defaults_repo_from_inventory(tmp_path, full_inventory, capsys):
    path = _inventory_file(tmp_path, full_inventory)
    assert checklist.main([str(path), "--gitlab-path", "g/p", "--tier", "premium"]) == 0
    out = capsys.readouterr().out
    assert "Source: `acme/proj`" in out
    assert "Target: `g/p` on `gitlab.com` (SaaS)" in out
    assert "GitLab tier: premium" in out


def test_cli_reads_stdin(monkeypatch, full_inventory, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(full_inventory)))
    assert checklist.main(["-"]) == 0
    assert "# Cutover checklist" in capsys.readouterr().out


def test_cli_unknown_origin_uses_placeholder(tmp_path, bare_inventory, capsys):
    path = _inventory_file(tmp_path, bare_inventory)
    assert checklist.main([str(path)]) == 0
    assert "OWNER/NAME" in capsys.readouterr().out


def test_cli_missing_file(tmp_path, capsys):
    missing = tmp_path / "none.json"
    assert checklist.main([str(missing)]) == 2
    err = capsys.readouterr().err
    assert str(missing) in err
    assert "inventory_github_repo.py" in err


def test_cli_invalid_json(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert checklist.main([str(bad)]) == 2
    err = capsys.readouterr().err
    assert str(bad) in err and "not valid JSON" in err and "--format json" in err


def test_cli_wrong_schema(tmp_path, capsys):
    other = tmp_path / "other.json"
    other.write_text(json.dumps({"schema": "something-else/1"}))
    assert checklist.main([str(other)]) == 2
    err = capsys.readouterr().err
    assert "not an inventory" in err and "Regenerate" in err


def test_cli_json_list_is_rejected(tmp_path, capsys):
    other = tmp_path / "list.json"
    other.write_text("[1, 2]")
    assert checklist.main([str(other)]) == 2
    assert "not an inventory" in capsys.readouterr().err


def test_cli_bad_tier_value_exits_nonzero(tmp_path, bare_inventory):
    path = _inventory_file(tmp_path, bare_inventory)
    with pytest.raises(SystemExit) as err:
        checklist.main([str(path), "--tier", "gold"])
    assert err.value.code == 2


def test_script_is_executable_with_shebang():
    script = SCRIPTS / "render_cutover_checklist.py"
    assert script.read_text().startswith("#!/usr/bin/env python3\n")
    assert script.stat().st_mode & 0o111
