"""Tests for inventory_model_calls.py on a synthetic repository built in a temp directory."""
# ruff: noqa: E501

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "plugins/models/skills/model-usage-audit/scripts/inventory_model_calls.py"
)
SPEC = importlib.util.spec_from_file_location("inventory_model_calls", SCRIPT)
assert SPEC and SPEC.loader
inv = importlib.util.module_from_spec(SPEC)
sys.modules["inventory_model_calls"] = inv
SPEC.loader.exec_module(inv)

# Built by joining pieces so no literal key-shaped string sits in this file.
FAKE_ANTHROPIC_KEY = "sk-" + "ant-" + "api03-" + "A1b2C3d4E5f6G7h8I9j0K1l2"
FAKE_AWS_KEY = "AKIA" + "ABCDEFGHIJKLMNOP"


def write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def scan(root: Path, deprecations: dict[str, Any] | None = None) -> dict[str, Any]:
    return inv.scan(root, {k.lower(): v for k, v in (deprecations or {}).items()})


def sites(report: dict[str, Any], provider: str, kind: str) -> list[dict[str, Any]]:
    return [s for s in report["sites"] if s["provider"] == provider and s["kind"] == kind]


ANTHROPIC_PY = """\
import anthropic

client = anthropic.Anthropic(max_retries=3, timeout=30.0)

def ask(question):
    return client.messages.create(
        model="claude-sonnet-5-5",
        max_tokens=2000,
        messages=[{"role": "user", "content": question}],
    )
"""


# --- call sites ------------------------------------------------------------------------------


def test_anthropic_client_and_call_have_file_and_line(tmp_path: Path) -> None:
    write(tmp_path, "app/llm.py", ANTHROPIC_PY)
    report = scan(tmp_path)
    client = sites(report, "anthropic", "client")[0]
    call = sites(report, "anthropic", "call")[0]
    assert (client["file"], client["line"]) == ("app/llm.py", 3)
    assert (call["file"], call["line"]) == ("app/llm.py", 6)
    assert report["files_with_model_calls"] == ["app/llm.py"]


def test_client_line_does_not_borrow_settings_from_a_later_call(tmp_path: Path) -> None:
    write(tmp_path, "app/llm.py", ANTHROPIC_PY)
    client = sites(scan(tmp_path), "anthropic", "client")[0]
    assert "max_tokens" not in client["settings_in_call"]


def test_multiline_call_is_read_to_its_closing_parenthesis(tmp_path: Path) -> None:
    code = (
        "r = client.messages.create(\n    model='x',\n    messages=[],\n"
        "    cache_control={'type': 'ephemeral'},\n)\n"
        "later = dict(timeout=5, max_tokens=9)\n"
    )
    write(tmp_path, "a.py", "import anthropic\n" + code)
    call = sites(scan(tmp_path), "anthropic", "call")[0]
    assert call["settings_in_call"] == ["prompt_caching"]


def test_settings_near_a_call_are_listed(tmp_path: Path) -> None:
    write(tmp_path, "app/llm.py", ANTHROPIC_PY)
    call = sites(scan(tmp_path), "anthropic", "call")[0]
    assert "max_tokens" in call["settings_in_call"]
    assert "timeout" not in call["settings_in_call"]
    client = sites(scan(tmp_path), "anthropic", "client")[0]
    assert {"timeout", "retries"} <= set(client["settings_in_call"])


@pytest.mark.parametrize(
    ("rel", "code", "provider", "kind"),
    [
        ("a.py", "from openai import OpenAI\nc = OpenAI()\nc.chat.completions.create(model='x')", "openai", "call"),
        ("b.py", "import google.generativeai as g\nm = g.GenerativeModel('x')\nm.generate_content('hi')", "gemini", "call"),
        ("c.py", "import boto3\nr = boto3.client('bedrock-runtime')\nr.converse(modelId='x')", "bedrock", "call"),
        ("d.py", "from langchain_anthropic import ChatAnthropic\nm = ChatAnthropic(model='x')", "anthropic", "wrapper"),
        ("e.ts", "const r = await client.responses.create({ model: 'x' });", "openai", "call"),
        ("f.ts", "import { AnthropicVertex } from '@anthropic-ai/vertex-sdk';\nnew AnthropicVertex({})", "anthropic", "client"),
        ("g.sh", "curl https://api.anthropic.com/v1/messages", "anthropic", "endpoint"),
        ("h.py", "import litellm\nlitellm.completion(model='x')", "litellm", "wrapper"),
    ],
)  # fmt: skip
def test_each_provider_family_is_detected(
    tmp_path: Path, rel: str, code: str, provider: str, kind: str
) -> None:
    write(tmp_path, rel, code)
    assert sites(scan(tmp_path), provider, kind), f"{provider} {kind} not found"


def test_plain_code_has_no_sites(tmp_path: Path) -> None:
    write(tmp_path, "util.py", "def add(a, b):\n    return a + b\n")
    report = scan(tmp_path)
    assert report["sites"] == []
    assert report["provider_counts"] == {}


# --- model ids -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("model_id", "provider", "form"),
    [
        ("claude-sonnet-5-5", "anthropic", "undated"),
        ("claude-haiku-4-5-20251001", "anthropic", "dated"),
        ("claude-haiku-4-5@20251001", "anthropic", "dated"),
        ("claude-3-5-sonnet-latest", "anthropic", "latest-alias"),
        ("us.anthropic.claude-opus-5-5-v1:0", "anthropic", "undated"),
        ("gpt-4o-2024-08-06", "openai", "dated"),
        ("gpt-5", "openai", "undated"),
        ("gemini-3.5-flash", "gemini", "undated"),
        ("gemini-3.5-pro-preview-05-06", "gemini", "preview"),
    ],
)
def test_model_ids_and_their_form(tmp_path: Path, model_id: str, provider: str, form: str) -> None:
    write(tmp_path, "cfg.py", f'MODEL = "{model_id}"\n')
    found = scan(tmp_path)["model_ids"]
    assert [(m["id"], m["provider"], m["form"]) for m in found] == [(model_id, provider, form)]


def test_package_names_are_not_model_ids(tmp_path: Path) -> None:
    write(
        tmp_path,
        "pkg.py",
        "import claude_agent_sdk  # pip install claude-agent-sdk\nport = 'claude-501'\n",
    )
    assert scan(tmp_path)["model_ids"] == []


def test_deprecation_facts_annotate_matching_ids(tmp_path: Path) -> None:
    write(
        tmp_path,
        "cfg.py",
        'A = "claude-sonnet-4-5-20250929"\nB = "claude-sonnet-4-5@20250929"\n'
        'C = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"\nD = "claude-sonnet-5-5"\n',
    )
    facts = {"claude-sonnet-4-5-20250929": {"status": "deprecated", "retires": "2026-11-30"}}
    by_line = {m["line"]: m for m in scan(tmp_path, facts)["model_ids"]}
    assert by_line[1]["lifecycle"]["status"] == "deprecated"
    assert by_line[2]["lifecycle"]["retires"] == "2026-11-30"
    assert by_line[3]["lifecycle"]["status"] == "deprecated"
    assert "lifecycle" not in by_line[4]


# --- secrets and sensitive data --------------------------------------------------------------


def test_hardcoded_keys_are_found_and_never_printed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(
        tmp_path,
        "app/llm.py",
        f'import anthropic\nclient = anthropic.Anthropic(api_key="{FAKE_ANTHROPIC_KEY}")\n',
    )
    write(tmp_path, "infra/aws.py", f'KEY = "{FAKE_AWS_KEY}"\n')
    assert inv.main([str(tmp_path), "--json"]) == 0
    out = capsys.readouterr().out
    report = json.loads(out)
    kinds = {s["kind"] for s in report["secrets_in_files"]}
    assert {"Anthropic API key", "AWS access key id"} <= kinds
    assert FAKE_ANTHROPIC_KEY not in out
    assert FAKE_AWS_KEY not in out
    assert FAKE_ANTHROPIC_KEY[10:] not in out
    inv.main([str(tmp_path)])
    text = capsys.readouterr().out
    assert FAKE_ANTHROPIC_KEY not in text and FAKE_AWS_KEY not in text


def test_one_key_gives_one_secret_hit(tmp_path: Path) -> None:
    write(tmp_path, "app.py", f'client = X(api_key="{FAKE_ANTHROPIC_KEY}")\n')
    hits = scan(tmp_path)["secrets_in_files"]
    assert [h["kind"] for h in hits] == ["Anthropic API key"]


def test_placeholder_and_env_lookups_are_not_secrets(tmp_path: Path) -> None:
    write(
        tmp_path,
        "app.py",
        'import os\nc = X(api_key=os.environ["ANTHROPIC_API_KEY"])\nd = X(api_key="your-api-key-here")\n'
        'e = X(api_key="${API_KEY_FROM_VAULT}")\n',
    )
    assert scan(tmp_path)["secrets_in_files"] == []


def test_code_snippets_in_the_report_are_redacted(tmp_path: Path) -> None:
    write(tmp_path, "app.py", f'import anthropic\nbase_url = "https://x?k={FAKE_ANTHROPIC_KEY}"\n')
    dump = json.dumps(scan(tmp_path))
    assert FAKE_ANTHROPIC_KEY not in dump


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_tracked_env_file_is_reported_but_example_is_not(tmp_path: Path) -> None:
    write(tmp_path, ".env", "ANTHROPIC_API_KEY=\n")
    write(tmp_path, ".env.example", "ANTHROPIC_API_KEY=\n")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "-f", ".env", ".env.example"], check=True)
    assert scan(tmp_path)["tracked_env_files"] == [".env"]


def test_logging_of_prompts_and_sensitive_words_only_in_files_with_model_calls(
    tmp_path: Path,
) -> None:
    write(
        tmp_path,
        "app/llm.py",
        "import anthropic\nimport logging\nlogging.info('sending %s', prompt)\npatient_name = row.patient\n",
    )
    write(tmp_path, "app/other.py", "logging.info('sending %s', prompt)\npatient = 1\n")
    report = scan(tmp_path)
    assert [h["file"] for h in report["logging_hints"]] == ["app/llm.py"]
    assert {h["file"] for h in report["pii_word_hints"]} == {"app/llm.py"}


def test_sensitive_word_hint_matches_inside_identifiers(tmp_path: Path) -> None:
    write(tmp_path, "app.py", "import anthropic\ndef f(patient_note, cuisine):\n    pass\n")
    lines = {h["line"] for h in scan(tmp_path)["pii_word_hints"]}
    assert lines == {2}


def test_routing_hints_capture_region_and_base_url(tmp_path: Path) -> None:
    write(
        tmp_path,
        "app.py",
        'c = AnthropicVertex(project_id="p", region="us-east5")\nbase_url = "http://gw.internal"\n',
    )
    lines = {r["line"] for r in scan(tmp_path)["routing_hints"]}
    assert lines == {1, 2}


# --- dependencies and evals ------------------------------------------------------------------


def test_dependencies_come_from_manifests(tmp_path: Path) -> None:
    write(tmp_path, "requirements.txt", "anthropic==0.99.0\nopenai>=1.0\nrequests\n")
    write(
        tmp_path,
        "package.json",
        '{"dependencies": {"@anthropic-ai/sdk": "^1.2.3", "left-pad": "1.0.0"}}',
    )
    deps = {(d["file"], d["package"]) for d in scan(tmp_path)["dependencies"]}
    assert deps == {
        ("requirements.txt", "anthropic"),
        ("requirements.txt", "openai"),
        ("package.json", "@anthropic-ai/sdk"),
    }


def test_eval_files_and_frameworks_are_listed(tmp_path: Path) -> None:
    write(tmp_path, "evals/cases.jsonl", "{}")
    write(tmp_path, "tests/test_prompt_eval.py", "pass")
    write(tmp_path, "requirements.txt", "promptfoo\nanthropic\n")
    hints = scan(tmp_path)["eval_hints"]
    assert "evals/cases.jsonl" in hints["files"]
    assert "tests/test_prompt_eval.py" in hints["files"]
    assert hints["frameworks"] == ["promptfoo"]


# --- walking the tree ------------------------------------------------------------------------


def test_vendor_directories_binary_and_big_files_are_skipped(tmp_path: Path) -> None:
    write(tmp_path, "node_modules/x/index.js", "client.messages.create({})")
    write(tmp_path, "src/a.py", "import anthropic\n")
    (tmp_path / "src/blob.json").write_bytes(b"\0\0\0claude-opus-5-5")
    (tmp_path / "src/huge.json").write_text('{"m": "claude-opus-5-5"}' + " " * inv.MAX_FILE_BYTES)
    report = scan(tmp_path)
    assert report["files_with_model_calls"] == ["src/a.py"]
    assert report["skipped"]["binary"] == 1
    assert report["skipped"]["larger than 1 MB"] == 1


def test_a_linked_worktree_is_not_scanned_twice(tmp_path: Path) -> None:
    write(tmp_path, "src/a.py", "import anthropic\n")
    write(tmp_path, "wt/src/a.py", "import anthropic\n")
    (tmp_path / "wt" / ".git").write_text("gitdir: ../.git/worktrees/wt\n")
    report = scan(tmp_path)
    assert report["files_with_model_calls"] == ["src/a.py"]
    assert report["skipped"]["linked git worktree"] == 1


# --- command line ----------------------------------------------------------------------------


def test_missing_root_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert inv.main([str(tmp_path / "nope")]) == 2
    assert "Pass the repository path" in capsys.readouterr().err


def test_bad_deprecations_file_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bad = tmp_path / "dep.json"
    bad.write_text('{"nope": 1}')
    assert inv.main([str(tmp_path), "--deprecations", str(bad)]) == 2
    assert '"models" object' in capsys.readouterr().err


def test_urls_with_credentials_or_secret_parameters_are_redacted(tmp_path: Path) -> None:
    write(
        tmp_path,
        "app.py",
        "base_url = 'https://user:hunter2@gateway.internal/v1'\n"
        "endpoint = 'https://x.example/v1?key=abc123SECRET&alt=1'\n",
    )
    dump = json.dumps(scan(tmp_path))
    assert "hunter2" not in dump
    assert "abc123SECRET" not in dump
    assert "alt=1" in dump


def test_very_long_lines_are_truncated_before_matching(tmp_path: Path) -> None:
    write(tmp_path, "bundle.js", "x" * (inv.MAX_LINE_CHARS + 50) + " client.messages.create({})\n")
    assert scan(tmp_path)["sites"] == []


def test_json_out_writes_the_full_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(tmp_path, "app/llm.py", ANTHROPIC_PY)
    out = tmp_path / "result.json"
    assert inv.main([str(tmp_path), "--json-out", str(out)]) == 0
    assert "Call sites" in capsys.readouterr().out
    assert json.loads(out.read_text())["provider_counts"] == {"anthropic": 2}


def test_unwritable_json_out_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(tmp_path, "a.py", "import anthropic\n")
    assert inv.main([str(tmp_path), "--json-out", str(tmp_path / "no" / "dir" / "x.json")]) == 2
    assert "cannot write" in capsys.readouterr().err


def test_limit_caps_each_text_section(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(tmp_path, "cfg.py", "".join(f'M{i} = "gpt-5-{i}"\n' for i in range(10)))
    assert inv.main([str(tmp_path), "--limit", "3"]) == 0
    text = capsys.readouterr().out
    assert "7 more" in text


def test_text_report_lists_sections(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(tmp_path, "app/llm.py", ANTHROPIC_PY)
    assert inv.main([str(tmp_path)]) == 0
    text = capsys.readouterr().out
    for heading in ("Call sites", "Model ids", "Dependencies", "Routing hints", "Not covered"):
        assert heading in text
    assert "app/llm.py:6" in text
