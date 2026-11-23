"""check_context_budget.py lists what an agent loads, and fails past a size budget."""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import ModuleType

import pytest


@pytest.fixture(autouse=True)
def config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A Claude config folder of its own, so the tester's real memory index is never read."""
    path = tmp_path / "claude-config"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(path))
    return path


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    return root


def put(root: Path, rel: str, size: int = 100, text: str | None = None) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text if text is not None else "x" * size, encoding="utf-8")
    return path


def run(
    module: ModuleType, capsys: pytest.CaptureFixture[str], root: Path, *args: str
) -> tuple[int, str, str]:
    code = module.main([str(root), *args])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def report(module: ModuleType, capsys: pytest.CaptureFixture[str], root: Path, *args: str) -> dict:
    code, out, _ = run(module, capsys, root, "--json", *args)
    data = json.loads(out)
    assert code == (0 if data["ok"] else 1)
    return data


def paths(data: dict) -> list[str]:
    return [f["path"] for f in data["files"]]


def test_imports_are_followed_recursively_and_a_cycle_ends(
    check_context_budget: ModuleType, capsys: pytest.CaptureFixture[str], repo: Path
) -> None:
    put(repo, "CLAUDE.md", text="See @AGENTS.md and @docs/a.md\n")
    put(repo, "AGENTS.md", 10)
    put(repo, "docs/a.md", text="more: @b.md\n")
    put(repo, "docs/b.md", text="back: @a.md and @../CLAUDE.md\n")
    data = report(check_context_budget, capsys, repo)
    # Each file once, in load order: CLAUDE.md, its imports depth first, nothing twice.
    assert paths(data) == ["CLAUDE.md", "AGENTS.md", "docs/a.md", "docs/b.md"]


def test_an_at_sign_that_is_not_an_import_is_ignored(
    check_context_budget: ModuleType, capsys: pytest.CaptureFixture[str], repo: Path
) -> None:
    put(repo, "real.md", 10)
    text = "Use `@real.md` here, mail me@real.md, `@types/node`, @nowhere.md\n```\n@real.md\n```\n"
    put(repo, "CLAUDE.md", text=text)
    assert paths(report(check_context_budget, capsys, repo)) == ["CLAUDE.md"]


def test_nested_guides_on_the_way_to_each_folder_are_counted(
    check_context_budget: ModuleType, capsys: pytest.CaptureFixture[str], repo: Path
) -> None:
    put(repo, "AGENTS.md", 10)
    put(repo, "backend/AGENTS.md", 20)
    put(repo, "backend/api/CLAUDE.md", 30)
    put(repo, "backend/api/new_dir/notes.txt", 1)
    put(repo, "backend/other/AGENTS.md", 40)
    put(repo, "frontend/AGENTS.md", 50)
    data = report(check_context_budget, capsys, repo, "--path", "backend/api/new_dir")
    assert paths(data) == ["AGENTS.md", "backend/AGENTS.md", "backend/api/CLAUDE.md"]
    data = report(check_context_budget, capsys, repo, "--path", "backend/api", "--path", "frontend")
    assert paths(data) == [
        "AGENTS.md",
        "backend/AGENTS.md",
        "backend/api/CLAUDE.md",
        "frontend/AGENTS.md",
    ]


def test_the_memory_index_for_the_repo_is_found(
    check_context_budget: ModuleType,
    capsys: pytest.CaptureFixture[str],
    repo: Path,
    config_dir: Path,
) -> None:
    slug = re.sub(r"[^A-Za-z0-9]", "-", str(repo.resolve()))
    index = put(config_dir, f"projects/{slug}/memory/MEMORY.md", 400)
    other = put(config_dir, "projects/-some-other-repo/memory/MEMORY.md", 400)
    data = report(check_context_budget, capsys, repo)
    memory = [f for f in data["files"] if f["kind"] == "memory"]
    assert [Path(f["path"]) for f in memory] == [index.resolve()]
    assert other.resolve() not in [Path(p) for p in paths(data)]
    assert memory[0]["bytes"] == 400
    assert memory[0]["tokens_est"] == 100


def test_defaults_flag_the_file_and_the_total_and_name_the_excess(
    check_context_budget: ModuleType, capsys: pytest.CaptureFixture[str], repo: Path
) -> None:
    put(repo, "AGENTS.md", 40_001)
    put(repo, "a/AGENTS.md", 30_000)
    data = report(check_context_budget, capsys, repo, "--path", "a")
    assert data["limits"]["guide_bytes"] == 40_000
    assert data["limits"]["total_bytes"] == 60_000
    assert [(o["path"], o["over_by"]) for o in data["over_budget"]] == [("AGENTS.md", 1)]
    assert data["total_over_by"] == 10_001
    code, out, _ = run(check_context_budget, capsys, repo, "--path", "a")
    assert code == 1
    assert "OVER AGENTS.md: 40,001 B, 1 B past" in out
    assert "estimate" in out


def test_a_repo_config_overrides_the_limits(
    check_context_budget: ModuleType, capsys: pytest.CaptureFixture[str], repo: Path
) -> None:
    put(repo, "AGENTS.md", 500)
    assert run(check_context_budget, capsys, repo)[0] == 0
    put(repo, ".context-budget.toml", text="guide_bytes = 400\ntotal_bytes = 450\n")
    data = report(check_context_budget, capsys, repo)
    assert data["limits"]["guide_bytes"] == 400
    assert data["over_budget"][0]["over_by"] == 100
    put(repo, ".context-budget.toml", text="guide_bytes = 1000\ntotal_bytes = 450\n")
    assert report(check_context_budget, capsys, repo)["total_over_by"] == 50


def test_a_baselined_file_is_held_where_it_is_and_cannot_grow(
    check_context_budget: ModuleType, capsys: pytest.CaptureFixture[str], repo: Path
) -> None:
    put(repo, ".context-budget.toml", text='[baseline]\n"AGENTS.md" = 500000\n')
    guide = put(repo, "AGENTS.md", 500_000)
    assert run(check_context_budget, capsys, repo)[0] == 0
    guide.write_text("x" * 500_001, encoding="utf-8")
    data = report(check_context_budget, capsys, repo)
    assert data["over_budget"] == [
        {
            "path": "AGENTS.md",
            "bytes": 500_001,
            "limit": 500_000,
            "over_by": 1,
            "baselined": True,
        }
    ]


def test_write_baseline_adds_and_lowers_entries_but_never_raises_one(
    check_context_budget: ModuleType, capsys: pytest.CaptureFixture[str], repo: Path
) -> None:
    put(repo, "AGENTS.md", 90_000)
    put(repo, "big/AGENTS.md", 70_000)
    put(repo, "small/AGENTS.md", 10_000)
    put(repo, ".context-budget.toml", text='[baseline]\n"big/AGENTS.md" = 80000\n"gone.md" = 5\n')
    run(check_context_budget, capsys, repo, "--path", "big", "--path", "small", "--write-baseline")
    config = (repo / ".context-budget.toml").read_text(encoding="utf-8")
    assert '"AGENTS.md" = 90000' in config
    assert '"big/AGENTS.md" = 70000' in config
    assert "small" not in config
    assert "gone.md" not in config
    # A file that has grown past its entry is refused; the write leaves the entry as it was.
    put(repo, "big/AGENTS.md", 75_000)
    run(check_context_budget, capsys, repo, "--path", "big", "--write-baseline")
    assert '"big/AGENTS.md" = 70000' in (repo / ".context-budget.toml").read_text(encoding="utf-8")
    assert run(check_context_budget, capsys, repo, "--path", "big")[0] == 1


def test_a_baseline_above_its_file_fails_until_lowered(
    check_context_budget: ModuleType, capsys: pytest.CaptureFixture[str], repo: Path
) -> None:
    put(repo, ".context-budget.toml", text='[baseline]\n"AGENTS.md" = 50000\n')
    put(repo, "AGENTS.md", 45_000)
    code, out, _ = run(check_context_budget, capsys, repo)
    assert code == 1
    assert "STALE AGENTS.md" in out
    run(check_context_budget, capsys, repo, "--write-baseline")
    assert run(check_context_budget, capsys, repo)[0] == 0


def test_write_baseline_keeps_entries_for_guides_it_did_not_measure(
    check_context_budget: ModuleType, capsys: pytest.CaptureFixture[str], repo: Path
) -> None:
    put(repo, "docs/AGENTS.md", 10)
    put(repo, "apps/AGENTS.md", 50_000)
    put(repo, ".context-budget.toml", text='[baseline]\n"apps/AGENTS.md" = 50000\n')
    run(check_context_budget, capsys, repo, "--path", "docs", "--write-baseline")
    assert '"apps/AGENTS.md" = 50000' in (repo / ".context-budget.toml").read_text("utf-8")


def test_all_enforces_each_file_but_not_the_total(
    check_context_budget: ModuleType, capsys: pytest.CaptureFixture[str], repo: Path
) -> None:
    for area in "abc":
        put(repo, f"{area}/AGENTS.md", 30_000)
    data = report(check_context_budget, capsys, repo, "--all")
    assert data["total_bytes"] == 90_000
    assert data["ok"] is True


def test_a_symlinked_config_is_refused_and_its_target_left_untouched(
    check_context_budget: ModuleType, capsys: pytest.CaptureFixture[str], repo: Path, tmp_path: Path
) -> None:
    victim = put(tmp_path, "victim.txt", text="keep me\n")
    (repo / ".context-budget.toml").symlink_to(victim)
    put(repo, "AGENTS.md", 50_000)
    code, _, err = run(check_context_budget, capsys, repo, "--write-baseline")
    assert code == 2
    assert "symlink" in err
    assert victim.read_text(encoding="utf-8") == "keep me\n"


def test_a_missing_path_folder_exits_2(
    check_context_budget: ModuleType, capsys: pytest.CaptureFixture[str], repo: Path
) -> None:
    code, _, err = run(check_context_budget, capsys, repo, "--path", "typo")
    assert code == 2
    assert "no such folder" in err


@pytest.mark.parametrize(
    "setup",
    ["no_root", "path_outside", "bad_toml", "bad_value"],
)
def test_usage_errors_exit_2_and_name_the_problem(
    check_context_budget: ModuleType,
    capsys: pytest.CaptureFixture[str],
    repo: Path,
    tmp_path: Path,
    setup: str,
) -> None:
    args: list[str] = []
    root = repo
    if setup == "no_root":
        root = tmp_path / "missing"
    elif setup == "path_outside":
        args = ["--path", ".."]
    elif setup == "bad_toml":
        put(repo, ".context-budget.toml", text="guide_bytes = = 3")
    else:
        put(repo, ".context-budget.toml", text='guide_bytes = "big"\n')
    code, out, err = run(check_context_budget, capsys, root, *args)
    assert code == 2
    assert out == ""
    assert "check_context_budget.py:" in err


def test_an_unknown_flag_exits_2(
    check_context_budget: ModuleType, capsys: pytest.CaptureFixture[str], repo: Path
) -> None:
    assert run(check_context_budget, capsys, repo, "--nope")[0] == 2


def test_json_report_has_the_documented_shape(
    check_context_budget: ModuleType, capsys: pytest.CaptureFixture[str], repo: Path
) -> None:
    put(repo, "CLAUDE.md", 8)
    data = report(check_context_budget, capsys, repo)
    assert set(data) == {
        "limits",
        "token_estimate",
        "files",
        "total_bytes",
        "total_tokens_est",
        "large",
        "over_budget",
        "stale_baseline",
        "total_over_by",
        "ok",
    }
    assert data["files"] == [{"path": "CLAUDE.md", "kind": "claude", "bytes": 8, "tokens_est": 2}]
    assert data["ok"] is True


def test_all_counts_every_guide_in_the_repo_but_no_dependencies_or_memory(
    check_context_budget: ModuleType,
    capsys: pytest.CaptureFixture[str],
    repo: Path,
    config_dir: Path,
) -> None:
    put(repo, "AGENTS.md", 10)
    put(repo, "a/b/AGENTS.md", 10)
    put(repo, "c/CLAUDE.md", 10)
    put(repo, "node_modules/pkg/AGENTS.md", 10)
    slug = re.sub(r"[^A-Za-z0-9]", "-", str(repo.resolve()))
    put(config_dir, f"projects/{slug}/memory/MEMORY.md", 10)
    data = report(check_context_budget, capsys, repo, "--all")
    assert paths(data) == ["AGENTS.md", "a/b/AGENTS.md", "c/CLAUDE.md"]


def test_write_baseline_never_records_a_file_outside_the_repo(
    check_context_budget: ModuleType,
    capsys: pytest.CaptureFixture[str],
    repo: Path,
    tmp_path: Path,
) -> None:
    outside = put(tmp_path, "elsewhere/notes.md", 50_000)
    put(repo, "CLAUDE.md", text=f"@{outside}\n")
    run(check_context_budget, capsys, repo, "--write-baseline")
    assert "elsewhere" not in (repo / ".context-budget.toml").read_text(encoding="utf-8")


def test_all_in_a_git_repo_skips_ignored_guides(
    check_context_budget: ModuleType, capsys: pytest.CaptureFixture[str], make_repo
) -> None:
    root = make_repo(
        {
            ".gitignore": "vendor/\n",
            "AGENTS.md": "x",
            "docs/AGENTS.md": "x",
            "vendor/AGENTS.md": "x",
        }
    )
    assert paths(report(check_context_budget, capsys, root, "--all")) == [
        "AGENTS.md",
        "docs/AGENTS.md",
    ]


def test_the_dot_claude_guide_and_its_imports_are_counted(
    check_context_budget: ModuleType, capsys: pytest.CaptureFixture[str], repo: Path
) -> None:
    put(repo, ".claude/CLAUDE.md", text="@notes.md\n")
    put(repo, ".claude/notes.md", 10)
    assert paths(report(check_context_budget, capsys, repo)) == [
        ".claude/CLAUDE.md",
        ".claude/notes.md",
    ]


def test_write_baseline_keeps_a_non_ascii_path_readable(
    check_context_budget: ModuleType, capsys: pytest.CaptureFixture[str], repo: Path
) -> None:
    put(repo, "\U0001f4d8/AGENTS.md", 50_000)
    run(check_context_budget, capsys, repo, "--all", "--write-baseline")
    assert run(check_context_budget, capsys, repo, "--all")[0] == 0


def test_all_in_a_git_repo_skips_dependency_folders(
    check_context_budget: ModuleType, capsys: pytest.CaptureFixture[str], make_repo
) -> None:
    root = make_repo({"AGENTS.md": "x", "node_modules/pkg/AGENTS.md": "x"})
    assert paths(report(check_context_budget, capsys, root, "--all")) == ["AGENTS.md"]
