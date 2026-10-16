"""Tests for the read-only gcloud wrapper. gcloud is never called."""

from __future__ import annotations

import importlib.util
import io
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "plugins/secure-build/skills/gcp-review/scripts/gcloud_readonly.py"
)
spec = importlib.util.spec_from_file_location("gcp_review_gcloud_readonly", SCRIPT)
assert spec is not None and spec.loader is not None
wrapper = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = wrapper
spec.loader.exec_module(wrapper)


def reject(argv: list[str]) -> str:
    with pytest.raises(wrapper.ReadOnlyViolation) as info:
        wrapper.validate(argv)
    return str(info.value)


class TestAcceptedCommands:
    @pytest.mark.parametrize(
        "argv",
        [
            ["projects", "describe", "my-project"],
            ["projects", "get-iam-policy", "my-project"],
            ["projects", "get-ancestors", "my-project"],
            ["organizations", "get-iam-policy", "123456"],
            ["resource-manager", "folders", "get-iam-policy", "456"],
            ["iam", "service-accounts", "list", "--project=p"],
            [
                "iam",
                "service-accounts",
                "keys",
                "list",
                "--iam-account=a@p.iam.gserviceaccount.com",
            ],
            ["iam", "workload-identity-pools", "providers", "list", "--location=global"],
            ["org-policies", "describe", "iam.disableServiceAccountKeyCreation", "--project=p"],
            ["org-policies", "list", "--project", "p"],
            ["access-context-manager", "perimeters", "list", "--policy=123"],
            ["container", "clusters", "list", "--project=p"],
            ["run", "services", "get-iam-policy", "svc", "--region=us-central1"],
            ["artifacts", "repositories", "list", "--project=p"],
            ["storage", "buckets", "list", "--raw", "--project=p"],
            ["services", "list", "--enabled", "--project=p"],
            ["asset", "search-all-iam-policies", "--scope=projects/p", "--query=policy:allUsers"],
            ["assured", "workloads", "list", "--organization=1", "--location=us"],
            [
                "assured",
                "workloads",
                "violations",
                "list",
                "--organization=1",
                "--location=us",
                "--workload=w",
            ],
            ["version"],
            ["config", "get-value", "account"],
            ["gcloud", "projects", "list"],
        ],
    )
    def test_read_commands_are_accepted(self, argv: list[str]) -> None:
        final = wrapper.validate(argv)
        assert "--quiet" in final
        assert final[0] != "gcloud"

    def test_json_format_is_added(self) -> None:
        assert "--format=json" in wrapper.validate(["projects", "list"])

    @pytest.mark.parametrize(
        "argv",
        [
            ["container", "binauthz", "policy", "export", "--project=p"],
            ["config", "get-value", "project"],
        ],
    )
    def test_text_commands_skip_json_format(self, argv: list[str]) -> None:
        final = wrapper.validate(argv)
        assert "--format=json" not in final
        assert wrapper.is_text_output(argv)

    def test_flag_and_value_forms_are_normalized(self) -> None:
        final = wrapper.validate(["projects", "list", "--limit", "5"])
        assert "--limit=5" in final

    def test_filter_value_may_contain_spaces(self) -> None:
        final = wrapper.validate(["services", "list", "--filter=state:ENABLED AND name:run*"])
        assert "--filter=state:ENABLED AND name:run*" in final


class TestMutatingCommandsAreRejected:
    @pytest.mark.parametrize(
        "argv",
        [
            ["projects", "set-iam-policy", "p", "policy.json"],
            [
                "projects",
                "add-iam-policy-binding",
                "p",
                "--member=user:a@b.c",
                "--role=roles/owner",
            ],
            ["projects", "remove-iam-policy-binding", "p", "--member=user:a@b.c", "--role=roles/x"],
            ["iam", "service-accounts", "create", "sa"],
            ["iam", "service-accounts", "delete", "sa@p.iam.gserviceaccount.com"],
            ["iam", "service-accounts", "keys", "create", "key.json", "--iam-account=a@p"],
            ["iam", "service-accounts", "keys", "delete", "k", "--iam-account=a@p"],
            ["iam", "service-accounts", "keys", "disable", "k", "--iam-account=a@p"],
            ["services", "enable", "run.googleapis.com"],
            ["services", "disable", "run.googleapis.com"],
            ["compute", "instances", "delete", "vm"],
            ["compute", "instances", "update", "vm"],
            ["compute", "ssh", "vm"],
            ["compute", "scp", "a", "b"],
            ["run", "deploy", "svc", "--image=x"],
            ["run", "services", "update", "svc"],
            ["container", "clusters", "update", "c"],
            ["container", "clusters", "get-credentials", "c"],
            ["container", "binauthz", "policy", "import", "f.yaml"],
            ["org-policies", "set-policy", "policy.yaml"],
            ["org-policies", "delete", "iam.x", "--project=p"],
            ["org-policies", "reset", "iam.x", "--project=p"],
            ["assured", "workloads", "create"],
            ["assured", "workloads", "update", "w"],
            ["assured", "workloads", "violations", "acknowledge"],
            ["storage", "buckets", "update", "gs://b"],
            ["storage", "rm", "gs://b/o"],
            ["sql", "instances", "patch", "i"],
            ["sql", "connect", "i"],
            ["asset", "export"],
            ["auth", "login"],
            ["auth", "print-access-token"],
            ["auth", "application-default", "login"],
            ["config", "set", "project", "p"],
            ["kms", "decrypt"],
        ],
    )
    def test_mutating_or_unlisted_commands_fail_closed(self, argv: list[str]) -> None:
        assert reject(argv).startswith("rejected:")

    def test_mutating_word_is_named_in_message(self) -> None:
        assert "set-iam-policy" in reject(["projects", "set-iam-policy", "p"])

    def test_unknown_command_message_points_to_allowlist(self) -> None:
        assert "ALLOWED_COMMANDS" in reject(["bigtable", "instances", "list"])

    def test_mutating_word_after_an_allowed_path_is_rejected(self) -> None:
        assert "mutating" in reject(["projects", "describe", "delete"])

    def test_alpha_and_beta_tracks_are_rejected(self) -> None:
        assert "release track" in reject(["beta", "projects", "list"])
        assert "release track" in reject(["alpha", "projects", "list"])


class TestUnsafeInput:
    def test_empty_argument_list_fails_closed(self) -> None:
        assert "no gcloud command" in reject([])

    def test_only_gcloud_word_fails_closed(self) -> None:
        assert "no gcloud command" in reject(["gcloud"])

    def test_only_flags_fail_closed(self) -> None:
        assert "no command word" in reject(["--project=p"])

    @pytest.mark.parametrize(
        "token",
        [
            "p;rm -rf /",
            "p && id",
            "p | cat",
            "`id`",
            "$(id)",
            "p>out",
            "p<in",
            "a\nb",
            "a\\b",
            "p'q",
            'p"q',
            "{x}",
            "(x)",
            "a\tb",
        ],
    )
    def test_shell_metacharacters_are_rejected(self, token: str) -> None:
        assert "shell syntax" in reject(["projects", "describe", token])

    def test_metacharacters_in_flag_values_are_rejected(self) -> None:
        assert "shell syntax" in reject(["projects", "list", "--filter=a;b"])

    def test_unsafe_positional_characters_are_rejected(self) -> None:
        assert "safe set" in reject(["projects", "describe", "a b"])

    def test_unsafe_flag_value_characters_are_rejected(self) -> None:
        assert "safe set" in reject(["projects", "list", "--limit=a b"])

    def test_too_many_positionals_are_rejected(self) -> None:
        assert "too many positional" in reject(["projects", "describe", "a", "b", "c"])

    def test_flag_without_value_is_rejected(self) -> None:
        assert "needs a value" in reject(["projects", "list", "--limit"])
        assert "needs a value" in reject(["projects", "list", "--limit", "--project=p"])

    def test_boolean_flag_with_value_is_rejected(self) -> None:
        assert "takes no value" in reject(["services", "list", "--enabled=true"])

    def test_unknown_flag_is_rejected_with_fix(self) -> None:
        message = reject(["projects", "list", "--some-new-flag"])
        assert "flag allowlist" in message and "VALUE_FLAGS" in message


class TestIdentityAndOutputFlags:
    @pytest.mark.parametrize(
        "flag",
        [
            "--impersonate-service-account=admin@p.iam.gserviceaccount.com",
            "--account=other@example.com",
            "--access-token-file=/tmp/token",
            "--credential-file-override=/tmp/key.json",
            "--configuration=other",
            "--format=yaml",
            "--flatten=bindings",
            "--quiet",
            "-q",
            "--verbosity=debug",
            "--log-http",
            "--billing-project=p",
        ],
    )
    def test_blocked_flags(self, flag: str) -> None:
        assert "not accepted" in reject(["projects", "list", flag])

    def test_impersonation_message_tells_the_user_what_to_do(self) -> None:
        message = reject(["projects", "list", "--impersonate-service-account=a@b.c"])
        assert "own gcloud configuration" in message


class TestExecution:
    def make_runner(self, returncode: int = 0, stdout: str = "[]", stderr: str = ""):
        seen: dict[str, object] = {}

        def runner(cmd: list[str], env: dict[str, str], timeout: float):
            seen.update(cmd=cmd, env=env, timeout=timeout)
            return wrapper.Outcome(returncode, stdout, stderr)

        return runner, seen

    def test_run_passes_validated_arguments_and_quiet_environment(self) -> None:
        runner, seen = self.make_runner()
        outcome = wrapper.run(["projects", "list"], timeout=7, runner=runner)
        assert outcome.returncode == 0
        assert seen["cmd"] == ["gcloud", "projects", "list", "--format=json", "--quiet"]
        assert seen["timeout"] == 7
        env = seen["env"]
        assert env["CLOUDSDK_CORE_DISABLE_PROMPTS"] == "1"
        assert env["CLOUDSDK_CORE_SHOULD_PROMPT_TO_ENABLE_API"] == "false"

    def test_run_does_not_call_the_runner_for_rejected_commands(self) -> None:
        runner, seen = self.make_runner()
        with pytest.raises(wrapper.ReadOnlyViolation):
            wrapper.run(["projects", "delete", "p"], runner=runner)
        assert seen == {}

    def test_missing_gcloud_names_the_fix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(wrapper.shutil, "which", lambda _name: None)
        with pytest.raises(wrapper.GcloudNotFound) as info:
            wrapper.run(["projects", "list"])
        assert "gcloud auth login" in str(info.value)

    def test_default_runner_closes_stdin_and_uses_no_shell(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: dict[str, object] = {}

        def fake_run(cmd, **kwargs):
            calls.update(cmd=cmd, **kwargs)
            return subprocess.CompletedProcess(cmd, 0, "[]", "")

        monkeypatch.setattr(wrapper.shutil, "which", lambda _name: "/usr/bin/gcloud")
        monkeypatch.setattr(wrapper.subprocess, "run", fake_run)
        wrapper.run(["projects", "list"])
        assert calls["stdin"] == subprocess.DEVNULL
        assert isinstance(calls["cmd"], list)
        assert "shell" not in calls

    def test_timeout_becomes_a_failed_outcome(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def runner(cmd, env, timeout):
            raise subprocess.TimeoutExpired(cmd, timeout)

        outcome = wrapper.run(["projects", "list"], timeout=1, runner=runner)
        assert outcome.returncode == 1 and "timed out" in outcome.stderr


class TestMain:
    def run_main(self, argv: list[str]) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = wrapper.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_rejected_command_exits_2_and_prints_reason(self) -> None:
        code, out, err = self.run_main(["projects", "delete", "p"])
        assert code == 2 and out == "" and "rejected" in err

    def test_empty_exits_2(self) -> None:
        code, _out, err = self.run_main([])
        assert code == 2 and "no gcloud command" in err

    def test_missing_gcloud_exits_3(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(wrapper.shutil, "which", lambda _name: None)
        code, _out, err = self.run_main(["projects", "list"])
        assert code == 3 and "not found" in err

    def test_success_prints_gcloud_output(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(wrapper.shutil, "which", lambda _name: "/usr/bin/gcloud")
        monkeypatch.setattr(
            wrapper.subprocess,
            "run",
            lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, '[{"a": 1}]', ""),
        )
        code, out, _err = self.run_main(["projects", "list"])
        assert code == 0 and out == '[{"a": 1}]'

    def test_gcloud_failure_exits_1_with_classification(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(wrapper.shutil, "which", lambda _name: "/usr/bin/gcloud")
        monkeypatch.setattr(
            wrapper.subprocess,
            "run",
            lambda cmd, **kw: subprocess.CompletedProcess(
                cmd, 1, "", "ERROR: (gcloud) PERMISSION_DENIED: The caller does not have permission"
            ),
        )
        code, _out, err = self.run_main(["projects", "list"])
        assert code == 1 and "classified=denied" in err


class TestClassification:
    @pytest.mark.parametrize(
        ("stderr", "expected"),
        [
            ("ERROR: PERMISSION_DENIED: caller does not have permission", "denied"),
            ("HTTPError 403: Forbidden", "denied"),
            ("API [run.googleapis.com] not enabled on project [p]", "not-enabled"),
            ("SERVICE_DISABLED: Cloud Run Admin API has not been used in project 1", "not-enabled"),
            ("ERROR: NOT_FOUND: constraint was not found", "not-found"),
            ("something else broke", "error"),
        ],
    )
    def test_classify_failure(self, stderr: str, expected: str) -> None:
        assert wrapper.classify_failure(stderr) == expected

    def test_not_enabled_wins_over_denied(self) -> None:
        text = "403 PERMISSION_DENIED: API has not been used in project 1 before"
        assert wrapper.classify_failure(text) == "not-enabled"

    def test_parse_output(self) -> None:
        assert wrapper.parse_output('{"a": 1}') == ({"a": 1}, None)
        assert wrapper.parse_output("   ") == ([], None)
        assert wrapper.parse_output("name: x") == (None, "name: x")


def test_script_is_executable_and_has_a_shebang() -> None:
    assert SCRIPT.read_text(encoding="utf-8").startswith("#!/usr/bin/env python3")
    assert SCRIPT.stat().st_mode & 0o111
