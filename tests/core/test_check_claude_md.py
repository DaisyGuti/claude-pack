"""check_claude_md.py accepts a good file and names every defect in a bad one."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "plugins/core/skills/project-setup/scripts"

GOOD = """# Example service

A small service used for tests.

## Commands

- Tests, all: `make test` (Makefile)
- Lint: `npm run lint` (package.json)

## Landing changes

- Branch from `main`, push the branch and open a pull request. Never commit to `main`.

## Security rules

- No secrets in code or prompts. See [the policy](SECURITY.md).
"""


def write(tmp_path: Path, text: str, **extra: str) -> Path:
    path = tmp_path / "CLAUDE.md"
    path.write_text(text, encoding="utf-8")
    for name, body in extra.items():
        (tmp_path / name.replace("__", "/")).write_text(body, encoding="utf-8")
    return path


def good_repo(tmp_path: Path, text: str = GOOD) -> Path:
    return write(
        tmp_path,
        text,
        **{
            "Makefile": "test:\n\tpytest\n",
            "package.json": json.dumps({"scripts": {"lint": "eslint ."}}),
            "SECURITY.md": "report\n",
        },
    )


def test_good_file_has_no_failures(check_claude_md, tmp_path):
    failures, notes = check_claude_md.check(good_repo(tmp_path))
    assert failures == []
    assert notes == []


def test_placeholders_and_template_comment_fail(check_claude_md, tmp_path):
    path = good_repo(tmp_path, GOOD + "\n- Install: `{{command}}`\n<!-- delete me -->\n")
    failures, _ = check_claude_md.check(path)
    assert sum("template placeholder" in f for f in failures) == 2


def test_over_the_line_limit_fails(check_claude_md, tmp_path):
    path = good_repo(tmp_path, GOOD + "\n".join(f"- rule {i}" for i in range(200)))
    failures, _ = check_claude_md.check(path)
    assert any("lines; the target is under 200" in f for f in failures)


def test_missing_sections_and_review_rule_fail(check_claude_md, tmp_path):
    path = write(tmp_path, "# Thin\n\nNothing here.\n")
    failures, _ = check_claude_md.check(path)
    text = "\n".join(failures)
    assert "Commands section" in text
    assert "Landing changes section" in text
    assert "Security rules section" in text
    assert "never mentions a pull request or merge request" in text


def test_merge_request_wording_satisfies_the_landing_rule(check_claude_md, tmp_path):
    path = good_repo(tmp_path, GOOD.replace("pull request", "merge request"))
    failures, _ = check_claude_md.check(path)
    assert failures == []


def test_secret_shapes_fail_without_echoing_the_value(check_claude_md, tmp_path):
    token = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4"
    path = good_repo(tmp_path, GOOD + f"\n- Deploy with {token}\n")
    failures, _ = check_claude_md.check(path)
    assert any("GitHub token" in f for f in failures)
    assert all(token not in f for f in failures)


def test_private_key_and_inline_credential_fail(check_claude_md, tmp_path):
    body = "\n-----BEGIN RSA PRIVATE KEY-----\napi_key = abcdefghijklmnop123\n"
    failures, _ = check_claude_md.check(good_repo(tmp_path, GOOD + body))
    joined = "\n".join(failures)
    assert "private key block" in joined
    assert "inline credential" in joined


def test_machine_paths_fail(check_claude_md, tmp_path):
    path = good_repo(tmp_path, GOOD + "\n- Config lives in /Users/someone/app\n")
    failures, _ = check_claude_md.check(path)
    assert any("machine-specific path" in f for f in failures)


def test_make_target_must_exist(check_claude_md, tmp_path):
    path = good_repo(tmp_path, GOOD + "\n- Release: `make release`\n")
    failures, _ = check_claude_md.check(path)
    assert any("no target 'release' in Makefile" in f for f in failures)


def test_make_without_makefile_fails(check_claude_md, tmp_path):
    path = write(tmp_path, GOOD)
    failures, _ = check_claude_md.check(path)
    assert any("there is no Makefile" in f for f in failures)


def test_package_scripts_must_exist_and_installs_are_ignored(check_claude_md, tmp_path):
    extra = "\n- Setup: `npm install` and `pnpm run build`\n- Audit: `npm audit`\n"
    path = good_repo(tmp_path, GOOD + extra)
    failures, _ = check_claude_md.check(path)
    script_failures = [f for f in failures if "script" in f]
    assert len(script_failures) == 1
    assert "`pnpm run build`: no script 'build' in package.json" in script_failures[0]


def test_links_and_imports_must_resolve(check_claude_md, tmp_path):
    text = GOOD + "\n[guide](docs/guide.md) [site](https://example.invalid) [top](#top)\n"
    path = good_repo(tmp_path, "@AGENTS.md\n" + text)
    failures, _ = check_claude_md.check(path)
    assert any("'AGENTS.md' does not exist" in f for f in failures)
    assert any("'docs/guide.md' does not exist" in f for f in failures)
    assert not any("example.invalid" in f or "#top" in f for f in failures)


def test_at_mentions_without_a_path_are_not_imports(check_claude_md, tmp_path):
    path = good_repo(tmp_path, "@reviewer please read this\n" + GOOD)
    failures, _ = check_claude_md.check(path)
    assert failures == []


def test_unknowns_and_unimported_agents_file_are_notes(check_claude_md, tmp_path):
    path = good_repo(tmp_path, GOOD + "\n- Build: UNKNOWN\n")
    (tmp_path / "AGENTS.md").write_text("rules\n", encoding="utf-8")
    failures, notes = check_claude_md.check(path)
    assert failures == []
    assert notes == [
        "1 UNKNOWN left for a person to fill in",
        "AGENTS.md exists; import it with a line '@AGENTS.md' instead of copying it",
    ]


def test_claude_dir_location_resolves_commands_from_the_repo_root(check_claude_md, tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / "Makefile").write_text("test:\n\tpytest\n", encoding="utf-8")
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"lint": "x"}}), encoding="utf-8")
    (tmp_path / "SECURITY.md").write_text("x\n", encoding="utf-8")
    path = tmp_path / ".claude" / "CLAUDE.md"
    path.write_text(GOOD.replace("](SECURITY.md)", "](../SECURITY.md)"), encoding="utf-8")
    failures, _ = check_claude_md.check(path)
    assert failures == []


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "check_claude_md.py"), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_exit_codes(tmp_path):
    ok = good_repo(tmp_path)
    assert run_cli(str(ok)).returncode == 0
    ok.write_text("# Thin\n", encoding="utf-8")
    bad = run_cli(str(ok))
    assert bad.returncode == 1
    assert "FAIL: missing a Commands section" in bad.stdout


def test_cli_missing_file_exits_2_with_the_fix(tmp_path):
    result = run_cli(str(tmp_path / "CLAUDE.md"))
    assert result.returncode == 2
    assert "cannot read" in result.stderr
    assert "Pass the path to a UTF-8 CLAUDE.md" in result.stderr


def test_cli_rejects_non_utf8_file(tmp_path):
    path = tmp_path / "CLAUDE.md"
    path.write_bytes(b"\xff\xfe\x00bad")
    assert run_cli(str(path)).returncode == 2
