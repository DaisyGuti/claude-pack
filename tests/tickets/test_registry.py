"""Tests for scripts/registry.py: first-run creation, readiness checks, parsing, board URLs."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

PLUGIN = Path(__file__).resolve().parents[2] / "plugins" / "tickets"
SCRIPTS = PLUGIN / "scripts"


def load_script(name: str) -> ModuleType:
    """Import plugins/tickets/scripts/<name>.py (the scripts are not a package)."""
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(f"tickets_{name}", SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"tickets_{name}"] = module
    spec.loader.exec_module(module)
    return module


registry = load_script("registry")


@pytest.fixture(autouse=True)
def all_tools_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend every CLI is on PATH so readiness results do not depend on this machine."""
    monkeypatch.setattr(registry.shutil, "which", lambda name: f"/usr/bin/{name}")


def test_first_run_creates_the_registry_and_asks_to_fill_it_in(tmp_path: Path) -> None:
    code, payload = registry.ensure(tmp_path / "data")
    assert code == registry.EXIT_CREATED
    assert payload["status"] == "created"
    created = Path(payload["path"])
    assert created.read_text(encoding="utf-8") == (PLUGIN / "registry.example.md").read_text(
        encoding="utf-8"
    )


def test_example_values_left_in_place_are_reported(tmp_path: Path) -> None:
    registry.ensure(tmp_path / "data")
    code, payload = registry.ensure(tmp_path / "data")
    assert code == registry.EXIT_INCOMPLETE
    assert any("your-github-login" in p for p in payload["problems"])


def test_filled_registry_is_ready(filled_registry: Path) -> None:
    code, payload = registry.ensure(filled_registry)
    assert (code, payload["status"]) == (0, "ok")


def test_ensure_never_overwrites_an_existing_registry(filled_registry: Path) -> None:
    path = filled_registry / "registry.md"
    before = path.read_text(encoding="utf-8")
    registry.ensure(filled_registry)
    assert path.read_text(encoding="utf-8") == before


def test_unfilled_github_subsection_does_not_block_a_gitlab_registry(filled_registry: Path) -> None:
    path = filled_registry / "registry.md"
    text = path.read_text(encoding="utf-8").replace("- Tracker: `github`", "- Tracker: `gitlab`")
    text = text.replace("- Host: `github.com`", "- Host: `gitlab.com`")
    path.write_text(text.replace("acme/shop-app", "acme-team/shop-app"), encoding="utf-8")
    code, payload = registry.ensure(filled_registry)
    assert (code, payload["status"]) == (0, "ok")


def test_missing_clone_folder_is_a_problem(filled_registry: Path) -> None:
    path = filled_registry / "registry.md"
    text = path.read_text(encoding="utf-8")
    clone = next(p for p in (filled_registry.parent / "code").iterdir())
    clone.rmdir()
    code, payload = registry.ensure(filled_registry)
    assert code == registry.EXIT_INCOMPLETE
    assert any("local clone" in p for p in payload["problems"])
    assert text  # the file itself is untouched


def test_missing_required_lane_is_a_problem(filled_registry: Path) -> None:
    path = filled_registry / "registry.md"
    lines = [
        ln for ln in path.read_text(encoding="utf-8").splitlines() if not ln.startswith("| ready ")
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    _, payload = registry.ensure(filled_registry)
    assert any("'ready'" in p for p in payload["problems"])


def test_unknown_tracker_is_a_problem(filled_registry: Path) -> None:
    path = filled_registry / "registry.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace("- Tracker: `github`", "- Tracker: `jira`"),
        encoding="utf-8",
    )
    _, payload = registry.ensure(filled_registry)
    assert any("'github' or 'gitlab'" in p for p in payload["problems"])


def test_parse_reads_the_trackers_lane_and_priority_columns(filled_registry: Path) -> None:
    text = (filled_registry / "registry.md").read_text(encoding="utf-8")
    github = registry.parse(text)
    assert github["lanes"]["in_progress"] == "In progress"
    assert github["priorities"][0] == {
        "role": "P0",
        "value": "P0",
        "meaning": github["priorities"][0]["meaning"],
    }
    gitlab = registry.parse(text.replace("- Tracker: `github`", "- Tracker: `gitlab`"))
    assert gitlab["lanes"]["in_progress"] == "status::in-progress"
    assert gitlab["priorities"][1]["value"] == "priority::1"


def test_parse_reads_board_labels_models_and_repos(filled_registry: Path) -> None:
    reg = registry.parse((filled_registry / "registry.md").read_text(encoding="utf-8"))
    assert reg["board"] == {"owner": "acme", "number": "1", "name": "Engineering"}
    assert reg["labels"]["run_worker"]["name"] == "run:worker"
    assert reg["model_labels"]["workhorse"]["label"] == "model:sonnet"
    assert reg["repos"][0]["name"] == "shop-app"
    assert reg["repos"][0]["remote"] == "acme/shop-app"
    assert "lane_meaning" in reg


def test_tilde_in_a_clone_path_expands_against_home(tmp_path: Path) -> None:
    text = (PLUGIN / "registry.example.md").read_text(encoding="utf-8")
    reg = registry.parse(text, home=tmp_path)
    assert reg["repos"][0]["clone"] == str(tmp_path / "code" / "my-app")


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "https://github.com/orgs/acme/projects/4/views/2",
            {"kind": "github-project", "owner": "acme", "number": 4},
        ),
        (
            "https://github.com/users/jo/projects/9",
            {"kind": "github-project", "owner": "jo", "number": 9},
        ),
        (
            "https://gitlab.com/groups/acme/sub/-/boards/12?label_name[]=x",
            {"kind": "gitlab-group", "scope": "group", "path": "acme/sub", "board_id": 12},
        ),
        (
            "https://gitlab.com/acme/app/-/boards/7",
            {"kind": "gitlab-project", "scope": "project", "path": "acme/app", "board_id": 7},
        ),
    ],
)
def test_board_urls_resolve(url: str, expected: dict[str, object]) -> None:
    host = url.split("/")[2]
    code, payload = registry.board_url(url, {"host": host})
    assert code == 0
    assert payload == expected


def test_board_url_on_another_host_is_refused() -> None:
    code, payload = registry.board_url(
        "https://gitlab.example.com/groups/a/-/boards/1", {"host": "gitlab.com"}
    )
    assert code == registry.EXIT_HOST_MISMATCH
    assert "gitlab.com" in payload["message"]


def test_unrecognized_url_is_refused_with_the_accepted_shapes() -> None:
    code, payload = registry.board_url("https://example.com/nothing", {"host": "example.com"})
    assert code == registry.EXIT_BAD_INPUT
    assert "Expected" in payload["message"]


def test_command_line_show_prints_json_for_a_ready_registry(filled_registry: Path) -> None:
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "registry.py"), "show", "--data-dir", str(filled_registry)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["tracker"] == "github"


def test_command_line_exit_code_is_3_on_first_run(tmp_path: Path) -> None:
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "registry.py"), "ensure", "--data-dir", str(tmp_path / "d")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 3
    assert json.loads(proc.stdout)["status"] == "created"


def test_missing_tracker_cli_is_a_problem_with_an_install_hint(
    filled_registry: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(registry.shutil, "which", lambda name: None if name == "gh" else "/bin/x")
    code, payload = registry.ensure(filled_registry)
    assert code == registry.EXIT_INCOMPLETE
    assert any("'gh' is not on PATH" in p and "gh auth login" in p for p in payload["problems"])


def test_gitlab_needs_glab_and_jq(filled_registry: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = filled_registry / "registry.md"
    text = path.read_text(encoding="utf-8").replace("- Tracker: `github`", "- Tracker: `gitlab`")
    path.write_text(text.replace("acme/shop-app", "acme-team/shop-app"), encoding="utf-8")
    monkeypatch.setattr(
        registry.shutil, "which", lambda name: None if name in {"glab", "jq"} else "/bin/x"
    )
    _, payload = registry.ensure(filled_registry)
    missing = [p for p in payload["problems"] if "is not on PATH" in p]
    assert len(missing) == 2
