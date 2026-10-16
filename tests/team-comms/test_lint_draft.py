"""Tests for scripts/lint_draft.py: writing rules and secret scan on synthetic text."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

# Built from pieces so no scanner reading this repo sees a credential-shaped literal.
AWS_KEY = "AKIA" + "IOSFODNN7EXAMPLE"
GITHUB_TOKEN = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"
SLACK_TOKEN = "xoxb-" + "123456789012-abcdefghij"


@pytest.fixture
def lint(load_script):
    return load_script("lint_draft")


def rules(findings) -> list[str]:
    return [f.rule for f in findings]


def test_plain_text_is_clean(lint) -> None:
    text = "The upload service retries failed writes three times.\nPlease review by Thursday."
    assert lint.check_prose(text) == []
    assert lint.check_secrets(text) == []


@pytest.mark.parametrize(
    "sentence",
    [
        "We measured it, not guessed it.",
        "This is a signal; not noise.",
        "It is not just a cache but a source of truth.",
        "This isn't a bug, it's a missing feature.",
        "Not a rewrite. A small patch.",
    ],
)
def test_contrast_constructions_are_flagged(lint, sentence: str) -> None:
    assert "contrast" in rules(lint.check_prose(sentence))


@pytest.mark.parametrize(
    "sentence",
    [
        "The cache is not enabled in staging.",
        "I did not change the schema.",
        "Notes on the rollout are in the doc.",
    ],
)
def test_plain_negation_is_not_flagged(lint, sentence: str) -> None:
    assert lint.check_prose(sentence) == []


def test_fenced_code_is_skipped_by_prose_rules(lint) -> None:
    text = "Run this:\n```sh\necho hi, not there\n```\nDone."
    assert lint.check_prose(text) == []


def test_inline_code_is_skipped_by_prose_rules(lint) -> None:
    assert lint.check_prose("Pass `--mode a, not b` to the tool.") == []


def test_hype_words_are_flagged(lint) -> None:
    findings = lint.check_prose("We will leverage a seamless, world-class pipeline.")
    assert rules(findings).count("hype") == 3


def test_placeholders_are_flagged(lint) -> None:
    findings = lint.check_prose("Owner: [TODO: name]\nETA: [confirm with Sam]")
    assert rules(findings) == ["placeholder", "placeholder"]


@pytest.mark.parametrize(
    ("text", "label"),
    [
        (f"key {AWS_KEY}", "aws-access-key-id"),
        (f"token {GITHUB_TOKEN}", "github-token"),
        (f"bot {SLACK_TOKEN}", "slack-token"),
        ("-----BEGIN RSA PRIVATE KEY-----", "private-key-block"),
        ("ssn 123-45-6789", "us-ssn-shaped-number"),
        ("password = hunter2hunter2", "secret-assignment"),
    ],
)
def test_secrets_are_flagged_and_masked(lint, text: str, label: str) -> None:
    findings = lint.check_secrets(text)
    assert len(findings) == 1
    assert label in findings[0].message
    assert findings[0].excerpt.endswith("...")
    assert AWS_KEY not in findings[0].excerpt
    assert GITHUB_TOKEN not in findings[0].excerpt


def test_env_lookup_is_not_a_secret(lint) -> None:
    assert lint.check_secrets('token = os.environ["API_TOKEN"]') == []


def test_secret_scan_covers_code_blocks(lint) -> None:
    text = f"```\nexport AWS_ACCESS_KEY_ID={AWS_KEY}\n```"
    assert rules(lint.check_secrets(text)) == ["secret"]


def run_cli(*args: str, stdin: str = "") -> subprocess.CompletedProcess[str]:
    script = Path(__file__).resolve().parents[2] / "plugins/team-comms/scripts/lint_draft.py"
    return subprocess.run(
        [sys.executable, str(script), *args], input=stdin, capture_output=True, text=True
    )


def test_cli_clean_exits_zero() -> None:
    result = run_cli("-", stdin="Ready for review.\n")
    assert result.returncode == 0
    assert "clean" in result.stdout


def test_cli_findings_exit_one_with_line_numbers() -> None:
    result = run_cli("-", stdin=f"fine line\nkey {AWS_KEY}\n")
    assert result.returncode == 1
    assert "<stdin>:2: secret:" in result.stdout
    assert AWS_KEY not in result.stdout


def test_cli_missing_file_exits_two_with_fix() -> None:
    result = run_cli("/no/such/draft.md")
    assert result.returncode == 2
    assert "no such file" in result.stderr
    assert "Pass a path" in result.stderr


def test_cli_flags_limit_the_checks() -> None:
    text = f"We leverage this. key {AWS_KEY}\n"
    assert run_cli("--no-prose", "-", stdin=text).returncode == 1
    assert "hype" not in run_cli("--no-prose", "-", stdin=text).stdout
    assert "secret" not in run_cli("--no-secrets", "-", stdin=text).stdout


def test_allow_placeholders_skips_only_the_placeholder_rule(lint) -> None:
    text = "ETA: [confirm with Sam]. We leverage this."
    assert sorted(rules(lint.check_prose(text))) == ["hype", "placeholder"]
    assert rules(lint.check_prose(text, allow_placeholders=True)) == ["hype"]


def test_cli_allow_placeholders_flag() -> None:
    text = "ETA: [confirm with Sam]\n"
    assert run_cli("-", stdin=text).returncode == 1
    assert run_cli("--allow-placeholders", "-", stdin=text).returncode == 0
