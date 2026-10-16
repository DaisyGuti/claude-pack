"""Tests for inventory_github_repo.py. Synthetic fixture trees only; no network."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "plugins/secure-build/skills/gitlab-migration/scripts/inventory_github_repo.py"


def _load():
    spec = importlib.util.spec_from_file_location("gitlab_migration_inventory", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


inv = _load()

CI_WORKFLOW = """\
name: CI
on:
  push:
    branches: [main, 'release/**']
  pull_request:
  schedule:
    - cron: '0 3 * * 1'
permissions:
  contents: read
env:
  LOG_LEVEL: debug
concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true
jobs:
  test:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-latest, macos-14]
        include:
          - os: ubuntu-latest
            extra: yes
    services:
      postgres:
        image: postgres:16
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
      - run: |
          npm ci
          echo "${{ secrets.NPM_TOKEN }}" # a comment
          gh pr comment 1 --body hi
  deploy:
    needs: test
    runs-on: [self-hosted, linux]
    environment: production
    permissions:
      id-token: write
      contents: read
    steps:
      - uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: projects/1/locations/global/pools/p/providers/g
          service_account: ${{ vars.DEPLOY_SA }}
      - uses: some-org/deploy-thing@v1
        env:
          KEY: ${{ secrets.DEPLOY_KEY }}
      - uses: ./.github/actions/local
"""


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def full_repo(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    _write(root, ".github/workflows/ci.yml", CI_WORKFLOW)
    _write(root, ".github/CODEOWNERS", "* @acme/platform\n/docs/ docs@example.com # docs\n")
    _write(
        root,
        ".github/dependabot.yml",
        "version: 2\nupdates:\n"
        "  - package-ecosystem: npm\n    directory: /\n    schedule:\n      interval: weekly\n"
        "    groups:\n      all:\n        patterns: ['*']\n"
        "  - package-ecosystem: github-actions\n    directory: /\n"
        "    schedule:\n      interval: monthly\n",
    )
    _write(root, ".github/ISSUE_TEMPLATE/bug.md", "bug")
    _write(root, ".github/FUNDING.yml", "github: [acme]\n")
    _write(
        root,
        ".gitmodules",
        '[submodule "lib"]\n\tpath = lib\n\turl = https://github.com/acme/lib.git\n',
    )
    _write(root, ".gitattributes", "*.psd filter=lfs diff=lfs merge=lfs -text\n")
    _write(
        root,
        "README.md",
        "# Proj\n[![CI](https://github.com/acme/proj/actions/workflows/ci.yml/badge.svg)]"
        "(https://github.com/acme/proj)\n"
        "See https://github.com/golang/go and ghcr.io/acme/proj:1\n",
    )
    _write(root, "go.mod", "module github.com/acme/proj\n")
    _write(
        root,
        ".git/config",
        '[remote "origin"]\n\turl = https://user:tok@github.com/acme/proj.git\n',
    )
    return root


# ------------------------------------------------------------------ YAML subset reader


def test_parse_block_map_and_sequences():
    doc = inv.parse_yaml_subset(
        "name: CI\non:\n  push:\n    branches:\n      - main\n      - dev\njobs:\n  a:\n"
        "    steps:\n      - run: echo hi\n      - uses: x/y@v1\n        with:\n          k: v\n"
    )
    assert doc["name"] == "CI"
    assert doc["on"]["push"]["branches"] == ["main", "dev"]
    steps = doc["jobs"]["a"]["steps"]
    assert steps[0] == {"run": "echo hi"}
    assert steps[1] == {"uses": "x/y@v1", "with": {"k": "v"}}


def test_parse_sequence_at_same_indent_as_key():
    doc = inv.parse_yaml_subset("branches:\n- main\n- dev\nother: 1\n")
    assert doc == {"branches": ["main", "dev"], "other": "1"}


def test_parse_flow_collections_and_quotes():
    doc = inv.parse_yaml_subset("a: [x, 'y z', \"q\"]\nb: {k: v, n: [1, 2]}\nc: 'it''s'\n")
    assert doc["a"] == ["x", "y z", "q"]
    assert doc["b"] == {"k": "v", "n": ["1", "2"]}
    assert doc["c"] == "it's"


def test_parse_block_scalar_keeps_lines():
    doc = inv.parse_yaml_subset("run: |\n  line one\n  line two\nnext: 1\n")
    assert doc["run"] == "line one\nline two"
    assert doc["next"] == "1"


def test_parse_expression_values_with_colons_and_hash_in_quotes():
    doc = inv.parse_yaml_subset(
        "if: ${{ github.ref == 'refs/heads/main' }}\nrun: echo \"a: b\" # trailing\n"
        "url: 'http://x/#frag'\n"
    )
    assert doc["if"] == "${{ github.ref == 'refs/heads/main' }}"
    assert doc["run"] == 'echo "a: b"'
    assert doc["url"] == "http://x/#frag"


def test_parse_comment_only_and_blank_lines_ignored():
    assert inv.parse_yaml_subset("# c\n\na: 1\n\n  # indented comment\nb: 2\n") == {
        "a": "1",
        "b": "2",
    }


def test_parse_empty_document_is_none():
    assert inv.parse_yaml_subset("# nothing\n") is None


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        ("a: &x 1\n", "anchors"),
        ("a: *x\n", "anchors"),
        ("a: !tag v\n", "anchors"),
        ("<<: {a: 1}\n", "merge"),
        ("a: 1\n---\nb: 2\n", "multi-document"),
        ("a: [1,\n  2]\n", "multi-line flow"),
        ("a: {b: 1,\n  c: 2}\n", "multi-line flow"),
        ("a:\n\tb: 1\n", "tab"),
        ("a: 'open\n", "unterminated"),
        ("just a scalar line\nmore\n", "expected"),
        ("a: 1\n    b: 2\n", "unexpected indentation"),
    ],
)
def test_parse_unsupported_raises_with_line(text, fragment):
    with pytest.raises(inv.YamlSubsetError) as err:
        inv.parse_yaml_subset(text)
    assert fragment in str(err.value)
    assert str(err.value).startswith("line ")


# ---------------------------------------------------------------- workflow analysis


def test_analyze_workflow_finds_structure():
    rec = inv.analyze_workflow(".github/workflows/ci.yml", CI_WORKFLOW)
    assert rec["parsed"] is True
    assert [t["event"] for t in rec["triggers"]] == ["push", "pull_request", "schedule"]
    assert rec["triggers"][0]["branches"] == ["main", "release/**"]
    assert rec["secrets"] == ["DEPLOY_KEY", "NPM_TOKEN"]
    assert rec["vars"] == ["DEPLOY_SA"]
    assert rec["id_token_write"] is True
    assert rec["env_names"] == ["LOG_LEVEL"]
    jobs = {j["id"]: j for j in rec["jobs"]}
    assert jobs["test"]["matrix_include_exclude"] == ["include"]
    assert jobs["test"]["services"] == ["postgres"]
    assert jobs["deploy"]["self_hosted"] is True
    assert jobs["deploy"]["environment"] == "production"
    assert jobs["deploy"]["needs"] == ["test"]
    assert jobs["deploy"]["google_auth_with_keys"] == [
        "service_account",
        "workload_identity_provider",
    ]
    ids = {f["id"] for f in rec["flags"]}
    assert {
        "gh-cli",
        "matrix-include-exclude",
        "oidc-id-token",
        "local-action",
        "third-party-action",
        "self-hosted-runner",
        "environment-deployment",
        "schedule-trigger",
        "concurrency",
    } <= ids


def test_analyze_workflow_never_copies_values():
    text = (
        "on: push\nenv:\n  PLAIN: supersecretvalue123\njobs:\n  a:\n    runs-on: ubuntu-latest\n"
        "    steps:\n      - run: echo hi\n        env:\n          T: ${{ secrets.A_TOKEN }}\n"
    )
    rec = inv.analyze_workflow("w.yml", text)
    assert "supersecretvalue123" not in json.dumps(rec)
    assert rec["env_names"] == ["PLAIN"]
    assert rec["secrets"] == ["A_TOKEN"]


def test_analyze_workflow_github_token_is_separate():
    rec = inv.analyze_workflow(
        "w.yml",
        "on: push\njobs:\n  a:\n    runs-on: x\n    steps:\n"
        "      - run: echo ${{ secrets.GITHUB_TOKEN }}\n",
    )
    assert rec["secrets"] == []
    assert rec["uses_github_token"] is True


def test_analyze_workflow_trigger_shapes():
    for text, expected in [
        ("on: push\njobs: {}\n", ["push"]),
        ("on: [push, pull_request]\njobs: {}\n", ["push", "pull_request"]),
        (
            "on:\n  workflow_dispatch:\n    inputs:\n      env:\n        type: string\njobs: {}\n",
            ["workflow_dispatch"],
        ),
    ]:
        rec = inv.analyze_workflow("w.yml", text)
        assert [t["event"] for t in rec["triggers"]] == expected


def test_analyze_workflow_pull_request_target_and_workflow_run_flagged():
    rec = inv.analyze_workflow(
        "w.yml", "on:\n  pull_request_target:\n  workflow_run:\n    workflows: [CI]\njobs: {}\n"
    )
    ids = {f["id"] for f in rec["flags"]}
    assert {"pull-request-target", "workflow-run"} <= ids


def test_analyze_workflow_reusable_call_and_inherit():
    text = (
        "on: push\njobs:\n  call:\n    uses: org/repo/.github/workflows/x.yml@v1\n"
        "    secrets: inherit\n"
    )
    rec = inv.analyze_workflow("w.yml", text)
    assert rec["secrets_inherit"] is True
    assert rec["jobs"][0]["reusable_workflow"] == "org/repo/.github/workflows/x.yml@v1"
    assert "reusable-workflow-call" in {f["id"] for f in rec["flags"]}


def test_analyze_workflow_dynamic_secret_name_flagged():
    rec = inv.analyze_workflow(
        "w.yml",
        "on: push\njobs:\n  a:\n    runs-on: x\n    steps:\n"
        "      - run: echo ${{ secrets[format('K_{0}', matrix.n)] }}\n",
    )
    assert "dynamic-secret-name" in {f["id"] for f in rec["flags"]}


def test_malformed_workflow_reports_could_not_parse_but_keeps_names():
    text = (
        "on: push\nbase: &b\n  k: v\njobs:\n  a:\n    steps:\n"
        "      - run: ${{ secrets.STILL_FOUND }}\n"
    )
    rec = inv.analyze_workflow("w.yml", text)
    assert rec["parsed"] is False
    assert "anchors" in rec["parse_error"]
    assert rec["secrets"] == ["STILL_FOUND"]
    flag = next(f for f in rec["flags"] if f["id"] == "parse-failed")
    assert "Could not parse" in flag["message"]


def test_workflow_with_non_mapping_top_level():
    rec = inv.analyze_workflow("w.yml", "- a\n- b\n")
    assert rec["parsed"] is False
    assert "mapping" in rec["parse_error"]


def test_workflow_without_jobs_flagged():
    rec = inv.analyze_workflow("w.yml", "on: push\n")
    assert rec["parsed"] is True
    assert "parse-failed" in {f["id"] for f in rec["flags"]}


def test_hosted_runner_labels_are_not_self_hosted():
    assert inv._is_self_hosted(["ubuntu-latest"]) is False
    assert inv._is_self_hosted(["ubuntu-22.04", "windows-2022"]) is False
    assert inv._is_self_hosted(["self-hosted"]) is True
    assert inv._is_self_hosted(["gpu-large"]) is True
    assert inv._is_self_hosted(["${{ matrix.os }}"]) is False


# ------------------------------------------------------------------ whole-repo inventory


def test_full_inventory(full_repo: Path):
    out = inv.build_inventory(full_repo)
    assert out["schema"].startswith("gitlab-migration-inventory/")
    assert out["origin"] == {"url": "https://github.com/acme/proj.git", "owner_repo": "acme/proj"}
    assert out["secret_names"] == ["DEPLOY_KEY", "NPM_TOKEN"]
    assert out["variable_names"] == ["DEPLOY_SA"]
    assert out["environments"] == ["production"]
    assert out["gcp_workload_identity"] is True
    assert out["has_github_dir"] is True
    assert out["lfs"]["used"] is True and out["lfs"]["patterns"] == ["*.psd"]
    assert out["submodules"][0]["github"] is True
    assert [m["path"] for m in out["submodules"]] == ["lib"]
    co = out["codeowners"]
    assert co["found"] == [".github/CODEOWNERS"]
    assert co["gitlab_ready"] is False
    assert co["team_owners"] == ["@acme/platform"]
    assert co["inline_comments"] == 1
    dep = out["dependabot"]
    assert [u["ecosystem"] for u in dep["updates"]] == ["npm", "github-actions"]
    assert dep["updates"][0]["extra_settings"] == ["groups"]
    paths = {e["path"] for e in out["github_extras"]}
    assert {".github/ISSUE_TEMPLATE", ".github/FUNDING.yml"} <= paths
    flag_ids = {f["id"] for f in out["flags"]}
    assert {
        "codeowners-location",
        "codeowners-teams",
        "codeowners-inline-comments",
        "dependabot",
        "lfs",
        "submodules-github",
        "registry-references",
        "go-module-path",
    } <= flag_ids
    assert {a["ref"] for a in out["actions_used"]} >= {
        "actions/checkout@v4",
        "./.github/actions/local",
    }


def test_origin_credentials_are_stripped(full_repo: Path):
    out = json.dumps(inv.build_inventory(full_repo))
    assert "tok@" not in out
    assert "user:tok" not in out


def test_references_split_own_and_other(full_repo: Path):
    refs = inv.build_inventory(full_repo)["references"]
    texts = [i["text"] for i in refs["items"]]
    assert "github.com/acme/proj" in texts
    assert not any("golang/go" in t for t in texts)
    assert refs["other_github_links_not_listed"] >= 1
    assert refs["counts"]["workflow-badge"] == 1
    assert refs["counts"]["ghcr"] == 1
    assert refs["go_module"] == "github.com/acme/proj"
    badge = next(i for i in refs["items"] if i["kind"] == "workflow-badge")
    assert badge["own_repo"] is True and badge["category"] == "docs"


def test_references_skip_vendor_dirs_binary_and_large(tmp_path: Path):
    root = tmp_path / "r"
    _write(root, "vendor/x/a.go", "import github.com/other/pkg\n")
    _write(root, "node_modules/y/b.js", "https://github.com/o/p\n")
    (root / "bin.dat").write_bytes(b"\0\0github.com/o/p\n")
    _write(root, "big.txt", "github.com/o/p\n" + "x" * (inv.MAX_SCAN_BYTES + 1))
    _write(root, "ok.md", "https://github.com/o/p\n")
    refs = inv.build_inventory(root)["references"]
    assert [i["file"] for i in refs["items"]] == ["ok.md"]
    assert refs["files_skipped_for_size"] == 1


def test_reference_list_is_capped_with_exact_counts(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(inv, "MAX_REFERENCES", 3)
    root = tmp_path / "r"
    _write(root, "a.md", "\n".join(f"ghcr.io/o/p{i}:1" for i in range(10)))
    refs = inv.build_inventory(root)["references"]
    assert len(refs["items"]) == 3
    assert refs["counts"]["ghcr"] == 10
    assert refs["truncated"] is True


def test_empty_repo_is_not_an_error(tmp_path: Path):
    root = tmp_path / "empty"
    root.mkdir()
    out = inv.build_inventory(root)
    assert out["workflows"] == []
    assert out["has_github_dir"] is False
    assert out["secret_names"] == []
    assert out["dependabot"] is None
    assert out["codeowners"]["found"] == []
    assert out["origin"]["url"] is None
    md = inv.render_markdown(out)
    assert "No `.github/` directory found" in md
    assert "No workflow files found" in md


def test_codeowners_in_gitlab_location_is_ready(tmp_path: Path):
    root = tmp_path / "r"
    _write(root, "docs/CODEOWNERS", "* @user\n")
    out = inv.build_inventory(root)
    assert out["codeowners"]["gitlab_ready"] is True
    assert "codeowners-location" not in {f["id"] for f in out["flags"]}


def test_malformed_dependabot_reports_parse_error(tmp_path: Path):
    root = tmp_path / "r"
    _write(root, ".github/dependabot.yml", "updates: &x\n  - a\n")
    dep = inv.build_inventory(root)["dependabot"]
    assert dep["parsed"] is False
    assert "anchors" in dep["parse_error"]
    assert "could not be parsed" in inv.render_markdown(inv.build_inventory(root))


def test_submodule_relative_url(tmp_path: Path):
    root = tmp_path / "r"
    _write(root, ".gitmodules", '[submodule "a"]\n\tpath = a\n\turl = ../a.git\n')
    mod = inv.build_inventory(root)["submodules"][0]
    assert mod["relative"] is True and mod["github"] is False


def test_lfsconfig_url_credentials_removed(tmp_path: Path):
    root = tmp_path / "r"
    _write(root, ".lfsconfig", "[lfs]\n\turl = https://u:p@lfs.example.com/x\n")
    lfs = inv.build_inventory(root)["lfs"]
    assert lfs["lfsconfig_present"] is True
    assert lfs["lfsconfig_url"] == "https://lfs.example.com/x"


def test_unreadable_workflow_directory_entries_are_ignored(tmp_path: Path):
    root = tmp_path / "r"
    _write(root, ".github/workflows/readme.txt", "not a workflow")
    (root / ".github/workflows/sub.yml").mkdir()
    assert inv.build_inventory(root)["workflows"] == []


def test_markdown_report_names_only(full_repo: Path):
    md = inv.render_markdown(inv.build_inventory(full_repo))
    assert "`NPM_TOKEN`" in md and "`DEPLOY_KEY`" in md
    assert "Needs a person" in md
    assert "tok@" not in md
    assert "projects/1/locations" not in md


# ------------------------------------------------------------------------------- CLI


def test_cli_markdown_default(full_repo: Path, capsys):
    assert inv.main([str(full_repo)]) == 0
    out = capsys.readouterr().out
    assert out.startswith("# GitHub repository inventory")


def test_cli_json_is_valid_and_json_out_written(full_repo: Path, tmp_path: Path, capsys):
    target = tmp_path / "out.json"
    assert inv.main([str(full_repo), "--format", "json", "--json-out", str(target)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed == json.loads(target.read_text())
    assert printed["schema"].startswith("gitlab-migration-inventory/")


def test_cli_both_prints_markdown_then_json(full_repo: Path, capsys):
    assert inv.main([str(full_repo), "--format", "both"]) == 0
    out = capsys.readouterr().out
    assert "# GitHub repository inventory" in out
    assert out.index("JSON inventory follows") < out.index('"schema"')


def test_cli_missing_path_names_input_and_fix(tmp_path: Path, capsys):
    missing = tmp_path / "nope"
    assert inv.main([str(missing)]) == 2
    err = capsys.readouterr().err
    assert str(missing) in err
    assert "Pass the root of a local checkout" in err


def test_cli_file_instead_of_directory(tmp_path: Path, capsys):
    f = tmp_path / "f.txt"
    f.write_text("x")
    assert inv.main([str(f)]) == 2
    assert "not a directory" in capsys.readouterr().err


def test_cli_unwritable_json_out(full_repo: Path, tmp_path: Path, capsys):
    bad = tmp_path / "missing_dir" / "out.json"
    assert inv.main([str(full_repo), "--json-out", str(bad)]) == 2
    err = capsys.readouterr().err
    assert str(bad) in err and "--json-out" in err


def test_script_is_executable_with_shebang():
    assert SCRIPT.read_text().startswith("#!/usr/bin/env python3\n")
    assert SCRIPT.stat().st_mode & 0o111


def test_symlinks_are_not_followed(tmp_path: Path):
    root = tmp_path / "r"
    outside = tmp_path / "outside.md"
    outside.write_text("https://github.com/o/p\n")
    root.mkdir()
    (root / "link.md").symlink_to(outside)
    refs = inv.build_inventory(root)["references"]
    assert refs["counts"] == {}


def test_origin_ssh_url_gives_owner_repo(tmp_path: Path):
    root = tmp_path / "r"
    _write(root, ".git/config", '[remote "origin"]\n\turl = git@github.com:acme/proj.git\n')
    origin = inv.build_inventory(root)["origin"]
    assert origin["owner_repo"] == "acme/proj"


def test_origin_on_another_host_has_no_owner_repo(tmp_path: Path):
    root = tmp_path / "r"
    _write(root, ".git/config", '[remote "origin"]\n\turl = https://git.example.org/a/b.git\n')
    origin = inv.build_inventory(root)["origin"]
    assert origin["url"] == "https://git.example.org/a/b.git"
    assert origin["owner_repo"] is None
