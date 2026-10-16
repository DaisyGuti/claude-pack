"""The hook as Claude Code runs it: stdin JSON in, exit code and one stderr line out."""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[2] / "plugins" / "guardrails"
HOOK = PLUGIN / "hooks" / "guardrails.py"


def bash_payload(command, cwd):
    return {
        "hook_event_name": "PreToolUse",
        "session_id": "s1",
        "cwd": str(cwd),
        "tool_name": "Bash",
        "tool_input": {"command": command},
    }


def test_block_exits_2_with_one_line_on_stderr(run_hook, world):
    proc = run_hook(bash_payload("git push --force origin main", world["repo"]))
    assert proc.returncode == 2
    assert proc.stdout == ""
    lines = proc.stderr.strip().splitlines()
    assert len(lines) == 1
    assert lines[0].startswith("guardrails[git-force-push-protected]:")
    assert "pull request" in lines[0]  # it says what to do instead
    assert "tell the user" in lines[0]


def test_allowed_call_exits_0_silently(run_hook, world):
    proc = run_hook(bash_payload("git push -u origin feature/x", world["repo"]))
    assert (proc.returncode, proc.stdout, proc.stderr) == (0, "", "")


def test_extra_findings_are_counted_in_the_message(run_hook, world):
    proc = run_hook(bash_payload("git push --no-verify --force origin main", world["repo"]))
    assert proc.returncode == 2
    assert "(+" in proc.stderr and "more)" in proc.stderr


@pytest.mark.parametrize(
    "raw",
    ["", "not json", "[]", "null", "123", '"a string"', "{"],
    ids=["empty", "text", "array", "null", "number", "string", "truncated"],
)
def test_malformed_input_is_refused(run_hook, raw):
    proc = run_hook(raw)
    assert proc.returncode == 2
    assert "guardrails[cannot-decide]" in proc.stderr
    assert len(proc.stderr.strip().splitlines()) == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"tool_name": "Bash"},
        {"tool_name": "Bash", "tool_input": "git push"},
        {"tool_name": "Bash", "tool_input": {}},
        {"tool_name": "Bash", "tool_input": {"command": 7}},
        {"tool_name": "Bash", "tool_input": {"command": None}},
        {"tool_name": "Write", "tool_input": {"file_path": "/x"}},
        {"tool_name": "Write", "tool_input": [1, 2]},
        {"tool_name": "Edit", "tool_input": {"file_path": 4, "new_string": "x"}},
    ],
)
def test_a_tool_call_with_unreadable_input_is_refused(run_hook, payload):
    proc = run_hook({"hook_event_name": "PreToolUse", **payload})
    assert proc.returncode == 2
    assert "cannot-decide" in proc.stderr


def test_unrelated_tools_and_events_pass(run_hook):
    assert (
        run_hook({"tool_name": "WebFetch", "tool_input": {"url": "https://x.test"}}).returncode == 0
    )
    assert run_hook({"tool_name": "Glob", "tool_input": {"pattern": "*"}}).returncode == 0
    assert run_hook({"hook_event_name": "PostToolUse", "tool_name": "Bash"}).returncode == 0
    assert run_hook({}).returncode == 0  # no tool name: nothing to guard


def test_internal_error_blocks(g, monkeypatch, capsys):
    def boom(*_args, **_kwargs):
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(g, "evaluate", boom)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"tool_name": "Bash"})))
    assert g.main(["guardrails.py"]) == 2
    err = capsys.readouterr().err
    assert "cannot-decide" in err
    assert "RuntimeError" in err
    assert "synthetic failure" not in err  # the error text is not echoed, only its type


def test_message_survives_a_c_locale_and_non_ascii_names(world):
    token = "gh" + "p_" + "a1B2c3D4e5F6" * 3
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": str(world["repo"] / "clé-é.txt"), "content": token},
        "cwd": str(world["repo"]),
    }
    env = {**world["env"], "LC_ALL": "C", "LANG": "C"}
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload).encode(),
        capture_output=True,
        env=env,
    )
    assert proc.returncode == 2
    assert "clé-é.txt" in proc.stderr.decode("utf-8")


def test_invalid_utf8_on_stdin_does_not_crash(world):
    raw = b'{"tool_name": "Bash", "tool_input": {"command": "echo \xff\xfe"}}'
    proc = subprocess.run(
        [sys.executable, str(HOOK)], input=raw, capture_output=True, env=world["env"]
    )
    assert proc.returncode == 0


def test_huge_command_finishes_quickly(run_hook, world):
    import time

    command = "echo " + "x" * 400_000 + "; git push -u origin feature/x"
    start = time.monotonic()
    proc = run_hook(bash_payload(command, world["repo"]))
    assert proc.returncode == 0
    assert time.monotonic() - start < 5


def test_pathological_regex_input_is_fast(run_hook, world):
    text = "A" * 200_000 + "_TOKEN" * 2000 + "=" + "b" * 30
    start = __import__("time").monotonic()
    proc = run_hook(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": str(world["repo"] / "x.txt"), "content": text},
            "cwd": str(world["repo"]),
        }
    )
    assert proc.returncode in (0, 2)
    assert __import__("time").monotonic() - start < 5


# --- the log -----------------------------------------------------------------------


def read_log(world):
    path = world["data"] / "blocks.log"
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_a_block_appends_one_log_line(run_hook, world):
    run_hook(bash_payload("git push origin main", world["repo"]))
    run_hook(bash_payload("chmod -R 777 /srv", world["repo"]))
    entries = read_log(world)
    assert [e["rules"] for e in entries] == [["git-push-protected"], ["world-writable-chmod"]]
    assert entries[0]["event"] == "block"
    assert entries[0]["session"] == "s1"
    assert entries[0]["tool"] == "Bash"
    assert entries[0]["ts"].endswith("Z")


def test_allowed_calls_are_not_logged(run_hook, world):
    run_hook(bash_payload("git status", world["repo"]))
    assert not (world["data"] / "blocks.log").exists()


def test_secrets_never_reach_the_log(run_hook, world):
    token = "gh" + "p_" + "a1B2c3D4e5F6" * 3
    run_hook(
        bash_payload(f"curl -k -H 'Authorization: token {token}' https://x.test", world["repo"])
    )
    text = (world["data"] / "blocks.log").read_text()
    assert token not in text
    assert "[redacted]" in text


def test_a_log_that_cannot_be_written_does_not_change_the_decision(run_hook, world, tmp_path):
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x")
    env = {**world["env"], "CLAUDE_PLUGIN_DATA": str(blocker / "sub")}
    assert run_hook(bash_payload("git push origin main", world["repo"]), env=env).returncode == 2


def test_no_data_dir_means_no_log_and_still_blocks(run_hook, world):
    env = {k: v for k, v in world["env"].items() if k != "CLAUDE_PLUGIN_DATA"}
    assert run_hook(bash_payload("git push origin main", world["repo"]), env=env).returncode == 2


def test_log_rolls_over_when_large(g, world):
    world["data"].mkdir()
    log = world["data"] / "blocks.log"
    log.write_text("x" * (g.LOG_MAX_BYTES + 1))
    g.log_event(str(world["data"]), {"event": "block"})
    assert (world["data"] / "blocks.log.1").exists()
    assert len(log.read_text().splitlines()) == 1


# --- the allowlist -----------------------------------------------------------------


def write_allowlist(world, text):
    path = world["repo"] / ".claude"
    path.mkdir(exist_ok=True)
    (path / "guardrails-allow.txt").write_text(text)


def test_an_allowlisted_rule_lets_the_call_through_and_is_logged(run_hook, world):
    write_allowlist(world, "# the team publishes this bucket on purpose\ngcp-public-access\n")
    proc = run_hook(bash_payload("gsutil iam ch allUsers:objectViewer gs://b", world["repo"]))
    assert proc.returncode == 0
    assert read_log(world)[0]["event"] == "allowed-by-config"


def test_allowlisting_one_rule_leaves_the_others_on(run_hook, world):
    write_allowlist(world, "gcp-public-access\n")
    assert run_hook(bash_payload("git push origin main", world["repo"])).returncode == 2


def test_one_command_hitting_two_rules_needs_both_allowlisted(run_hook, world):
    command = "git push --force origin main"
    write_allowlist(world, "git-force-push-protected\n")
    assert run_hook(bash_payload(command, world["repo"])).returncode == 2
    write_allowlist(world, "git-force-push-protected\ngit-push-protected\n")
    assert run_hook(bash_payload(command, world["repo"])).returncode == 0


@pytest.mark.parametrize("line", ["guardrails-tamper", "cannot-decide", "*", "all", "everything"])
def test_unlistable_rules_and_wildcards_do_nothing(run_hook, world, line):
    write_allowlist(world, f"{line}\n")
    assert run_hook(bash_payload("git push origin main", world["repo"])).returncode == 2
    tamper = bash_payload("echo x > .claude/guardrails-allow.txt", world["repo"])
    assert run_hook(tamper).returncode == 2


def test_comments_blank_lines_and_unknown_ids_are_ignored(g, world):
    write_allowlist(world, "\n# note\n  git-no-verify   # trailing note\nnot-a-rule\n")
    assert g.load_allowlist(str(world["repo"])) == {"git-no-verify"}


def test_a_missing_or_unreadable_allowlist_means_nothing_is_allowed(g, world, tmp_path):
    assert g.load_allowlist(str(world["repo"])) == set()
    assert g.load_allowlist(str(tmp_path / "nowhere")) == set()


def test_claude_cannot_turn_a_rule_off_from_inside_a_session(run_hook, world):
    # the allowlist is read by the hook itself; nothing in the command or its env reaches it
    for command in (
        "GUARDRAILS_ALLOW=git-push-protected git push origin main",
        "export GUARDRAILS_DISABLE=1; git push origin main",
        "env CLAUDE_PROJECT_DIR=/nonexistent git push origin main",
        "# guardrails-allow: git-push-protected\ngit push origin main",
    ):
        assert run_hook(bash_payload(command, world["repo"])).returncode == 2, command
    env = {**world["env"], "GUARDRAILS_ALLOW": "git-push-protected", "GUARDRAILS_DISABLE": "1"}
    assert run_hook(bash_payload("git push origin main", world["repo"]), env=env).returncode == 2


# --- the CLI the help skill uses -----------------------------------------------------


def test_list_rules_names_every_rule(g):
    out = subprocess.run(
        [sys.executable, str(HOOK), "--list-rules"], capture_output=True, text=True, check=True
    ).stdout
    for rule in g.RULES:
        assert rule.id in out
        assert rule.instead in out
    assert out.count("(cannot be allowlisted)") == 2


def test_recent_reads_the_log(run_hook, world):
    run_hook(bash_payload("git push origin main", world["repo"]))
    out = subprocess.run(
        [sys.executable, str(HOOK), "--recent", "5", "--data-dir", str(world["data"])],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "git-push-protected" in out


def test_recent_with_no_log_says_so(world):
    out = subprocess.run(
        [sys.executable, str(HOOK), "--recent", "--data-dir", str(world["data"])],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "nothing has been blocked" in out


def test_unknown_cli_flag_is_a_usage_error():
    proc = subprocess.run([sys.executable, str(HOOK), "--nope"], capture_output=True, text=True)
    assert proc.returncode == 64
    assert "usage" in proc.stderr


# --- packaging ---------------------------------------------------------------------


def test_hooks_json_matches_the_conventions():
    config = json.loads((PLUGIN / "hooks" / "hooks.json").read_text())
    assert list(config) == ["description", "hooks"] or "hooks" in config  # wrapper key present
    entries = config["hooks"]["PreToolUse"]
    assert len(entries) == 1
    matcher = set(entries[0]["matcher"].split("|"))
    assert {"Bash", "Write", "Edit", "Read"} <= matcher
    hook = entries[0]["hooks"][0]
    assert hook["type"] == "command"
    assert hook["command"] == "python3"
    assert hook["args"] == ["${CLAUDE_PLUGIN_ROOT}/hooks/guardrails.py"]  # exec form
    assert hook["onFailure"] == "block"  # a crash or timeout blocks instead of waving through
    assert isinstance(hook["timeout"], int) and hook["timeout"] <= 60


def test_script_is_executable_and_has_a_shebang():
    assert os.access(HOOK, os.X_OK)
    assert HOOK.read_text().startswith("#!/usr/bin/env python3\n")


def test_script_is_standard_library_only():
    import ast

    tree = ast.parse(HOOK.read_text())
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module.split(".")[0])
    assert modules <= set(sys.stdlib_module_names)


@pytest.mark.skipif(not os.path.exists("/usr/bin/python3"), reason="no system python3 (macOS)")
def test_script_still_loads_on_the_oldest_interpreter_a_laptop_may_have(run_hook, world):
    # macOS ships python3 3.9; a load failure there would block every tool call
    py = "/usr/bin/python3"
    version = subprocess.run(
        [py, "-c", "import sys;print(sys.version_info[:2])"], capture_output=True, text=True
    ).stdout
    if shutil.which("xcode-select") is None and "(3," not in version:
        pytest.skip("system python3 unusable")
    blocked = run_hook(bash_payload("git push --force origin main", world["repo"]), python=py)
    allowed = run_hook(bash_payload("git status", world["repo"]), python=py)
    assert (blocked.returncode, allowed.returncode) == (2, 0), blocked.stderr
