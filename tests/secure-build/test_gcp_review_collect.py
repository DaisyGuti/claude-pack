"""Tests for the evidence collector. A fake runner replaces gcloud; nothing runs a subprocess."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "plugins/secure-build/skills/gcp-review/scripts"


def load(filename: str, name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


collect = load("gcp_collect.py", "gcp_review_collect_under_test")
rules = load("gcp_rules.py", "gcp_review_rules_for_collect_test")
wrapper = sys.modules["gcloud_readonly"]  # loaded by the collector from the same folder

SA = "builder@acme.iam.gserviceaccount.com"


class FakeRunner:
    """Answers each argv from a table keyed by the command words; records every call."""

    def __init__(self, answers: dict[tuple[str, ...], Any] | None = None) -> None:
        self.answers = answers or {}
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str]):
        self.calls.append(argv)
        words = tuple(a for a in argv if not a.startswith("--"))
        for size in range(len(words), 0, -1):
            hit = self.answers.get(words[:size])
            if hit is not None:
                if isinstance(hit, collect.CallResult):
                    return hit
                return collect.CallResult("ok", data=hit)
        return collect.CallResult("ok", data=[])


def run(settings: Any, runner: FakeRunner) -> dict[str, Any]:
    return collect.collect(settings, runner)


def kinds(evidence: dict[str, Any]) -> list[str]:
    return [c["kind"] for c in evidence["calls"]]


class TestBattery:
    def test_every_battery_call_is_on_the_read_only_allowlist(self) -> None:
        runner = FakeRunner(
            {
                ("iam", "service-accounts", "list"): [{"email": SA}],
                ("run", "services", "list"): [
                    {
                        "metadata": {
                            "name": "web",
                            "labels": {"cloud.googleapis.com/location": "us-east1"},
                        }
                    }
                ],
                ("artifacts", "repositories", "list"): [
                    {"name": "projects/acme/locations/us/repositories/imgs"}
                ],
                ("iam", "workload-identity-pools", "list"): [
                    {"name": "projects/1/locations/global/workloadIdentityPools/ci"}
                ],
                ("access-context-manager", "policies", "list"): [{"name": "accessPolicies/9"}],
                ("assured", "workloads", "list"): [
                    {"name": "organizations/1/locations/us/workloads/w1"}
                ],
            }
        )
        settings = collect.Settings(projects=["acme"], organizations=["1"], folders=["2"])
        evidence = run(settings, runner)
        assert runner.calls, "the fake runner saw no calls"
        for argv in runner.calls:
            wrapper.validate(argv)  # raises if any call is not read-only
        seen = set(kinds(evidence))
        for expected in (
            "identity",
            "project-describe",
            "ancestors",
            "iam-policy",
            "service-accounts",
            "sa-keys",
            "sa-iam-policy",
            "org-policy",
            "services-enabled",
            "buckets",
            "sql-instances",
            "firewall-rules",
            "networks",
            "instances",
            "project-info",
            "clusters",
            "run-services",
            "run-iam-policy",
            "ar-repos",
            "ar-iam-policy",
            "binauthz-policy",
            "binauthz-attestors",
            "wif-pools",
            "wif-providers",
            "vpcsc-policies",
            "vpcsc-perimeters",
            "assured-workloads",
            "assured-violations",
        ):
            assert expected in seen, expected

    def test_no_mutating_word_appears_in_any_battery_call(self) -> None:
        runner = FakeRunner({("iam", "service-accounts", "list"): [{"email": SA}]})
        run(collect.Settings(projects=["acme"], organizations=["1"]), runner)
        words = {w for argv in runner.calls for w in argv if not w.startswith("--")}
        assert not words & wrapper.MUTATING_WORDS - {"export"}

    def test_org_policy_constraints_match_the_analyzer(self) -> None:
        assert set(collect.ORG_POLICY_CONSTRAINTS) == set(rules.ORG_CHECKS)

    def test_both_constraint_name_forms_are_queried(self) -> None:
        runner = FakeRunner()
        run(collect.Settings(projects=["acme"]), runner)
        queried = {a[2] for a in runner.calls if a[:2] == ["org-policies", "describe"]}
        assert "iam.disableServiceAccountKeyCreation" in queried
        assert "iam.managed.disableServiceAccountKeyCreation" in queried

    def test_per_service_account_calls_use_the_listed_emails(self) -> None:
        runner = FakeRunner({("iam", "service-accounts", "list"): [{"email": SA}]})
        evidence = run(collect.Settings(projects=["acme"]), runner)
        keys = [c for c in evidence["calls"] if c["kind"] == "sa-keys"]
        assert [c["key"] for c in keys] == [SA]
        assert f"--iam-account={SA}" in keys[0]["argv"]
        assert "--managed-by=user" in keys[0]["argv"]

    def test_service_account_calls_are_capped(self) -> None:
        accounts = [{"email": f"sa{i}@acme.iam.gserviceaccount.com"} for i in range(5)]
        runner = FakeRunner({("iam", "service-accounts", "list"): accounts})
        settings = collect.Settings(projects=["acme"], max_per_kind=2)
        evidence = run(settings, runner)
        assert len([c for c in evidence["calls"] if c["kind"] == "sa-keys"]) == 2

    def test_cloud_run_iam_call_uses_the_service_region(self) -> None:
        service = {
            "metadata": {"name": "web", "labels": {"cloud.googleapis.com/location": "us-east1"}}
        }
        runner = FakeRunner({("run", "services", "list"): [service]})
        evidence = run(collect.Settings(projects=["acme"]), runner)
        call = next(c for c in evidence["calls"] if c["kind"] == "run-iam-policy")
        assert call["key"] == "us-east1/web" and "--region=us-east1" in call["argv"]

    def test_artifact_registry_iam_call_parses_the_repository_name(self) -> None:
        repo = {"name": "projects/acme/locations/us-west1/repositories/imgs"}
        runner = FakeRunner({("artifacts", "repositories", "list"): [repo]})
        evidence = run(collect.Settings(projects=["acme"]), runner)
        call = next(c for c in evidence["calls"] if c["kind"] == "ar-iam-policy")
        assert call["argv"][3] == "imgs" and "--location=us-west1" in call["argv"]

    def test_workload_identity_providers_follow_each_pool(self) -> None:
        pool = {"name": "projects/1/locations/global/workloadIdentityPools/ci"}
        runner = FakeRunner({("iam", "workload-identity-pools", "list"): [pool]})
        evidence = run(collect.Settings(projects=["acme"]), runner)
        call = next(c for c in evidence["calls"] if c["kind"] == "wif-providers")
        assert call["key"] == "ci" and "--workload-identity-pool=ci" in call["argv"]

    def test_organization_scope_adds_org_calls_only_when_asked(self) -> None:
        evidence = run(collect.Settings(projects=["acme"]), FakeRunner())
        assert "vpcsc-policies" not in kinds(evidence)
        evidence = run(collect.Settings(projects=["acme"], organizations=["1"]), FakeRunner())
        assert "vpcsc-policies" in kinds(evidence)

    def test_assured_workloads_locations_are_configurable(self) -> None:
        settings = collect.Settings(organizations=["1"], assured_locations=["us", "europe-west1"])
        runner = FakeRunner()
        run(settings, runner)
        locations = {a[-1] for a in runner.calls if a[:3] == ["assured", "workloads", "list"]}
        assert locations == {"--location=us", "--location=europe-west1"}


class TestTolerantCollection:
    def test_denied_and_not_enabled_calls_are_recorded_and_collection_continues(self) -> None:
        runner = FakeRunner(
            {
                ("projects", "get-iam-policy"): collect.CallResult(
                    "denied", error="PERMISSION_DENIED"
                ),
                ("run", "services", "list"): collect.CallResult(
                    "not-enabled", error="API not enabled"
                ),
            }
        )
        evidence = run(collect.Settings(projects=["acme"]), runner)
        by_kind = {c["kind"]: c for c in evidence["calls"]}
        assert by_kind["iam-policy"]["status"] == "denied"
        assert by_kind["run-services"]["status"] == "not-enabled"
        assert by_kind["clusters"]["status"] == "ok"  # later calls still ran
        assert (
            by_kind["iam-policy"]["data"] is None
            and "PERMISSION_DENIED" in by_kind["iam-policy"]["error"]
        )

    def test_dependent_calls_are_skipped_when_the_listing_failed(self) -> None:
        runner = FakeRunner(
            {("iam", "service-accounts", "list"): collect.CallResult("denied", error="no")}
        )
        evidence = run(collect.Settings(projects=["acme"]), runner)
        assert "sa-keys" not in kinds(evidence)

    def test_malformed_listing_entries_are_ignored(self) -> None:
        runner = FakeRunner({("iam", "service-accounts", "list"): ["junk", {"no_email": 1}]})
        evidence = run(collect.Settings(projects=["acme"]), runner)
        assert "sa-keys" not in kinds(evidence)


class TestDefaultRunner:
    def make(self, monkeypatch: pytest.MonkeyPatch, returncode: int, stdout: str, stderr: str):
        outcome = wrapper.Outcome(returncode, stdout, stderr)
        monkeypatch.setattr(wrapper, "run", lambda argv, timeout=120.0, runner=None: outcome)
        return collect.gcloud_runner()

    def test_success_parses_json(self, monkeypatch: pytest.MonkeyPatch) -> None:
        result = self.make(monkeypatch, 0, '[{"a": 1}]', "")(["projects", "list"])
        assert result.status == "ok" and result.data == [{"a": 1}]

    def test_failure_is_classified(self, monkeypatch: pytest.MonkeyPatch) -> None:
        result = self.make(monkeypatch, 1, "", "PERMISSION_DENIED: no")(["projects", "list"])
        assert result.status == "denied"

    def test_non_json_output_is_a_gap_for_json_commands(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        result = self.make(monkeypatch, 0, "not json", "")(["projects", "list"])
        assert result.status == "unparseable" and result.text == "not json"

    def test_text_commands_keep_their_text(self, monkeypatch: pytest.MonkeyPatch) -> None:
        argv = ["container", "binauthz", "policy", "export", "--project=p"]
        result = self.make(
            monkeypatch, 0, "defaultAdmissionRule:\n  evaluationMode: ALWAYS_ALLOW\n", ""
        )(argv)
        assert result.status == "ok" and "ALWAYS_ALLOW" in result.text


class TestMain:
    def test_writes_an_evidence_file(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        out = tmp_path / "nested" / "evidence.json"
        code = collect.main(["--project", "acme", "--out", str(out)], runner=FakeRunner())
        assert code == 0
        doc = json.loads(out.read_text(encoding="utf-8"))
        assert doc["schema"] == "gcp-review-evidence/1"
        assert doc["scopes"]["projects"] == ["acme"]
        assert "ok=" in capsys.readouterr().out

    def test_no_scope_is_an_error_that_says_to_ask(self, tmp_path: Path, capsys) -> None:
        code = collect.main(["--out", str(tmp_path / "e.json")], runner=FakeRunner())
        assert code == 2 and "Ask the user" in capsys.readouterr().err

    def test_unwritable_output_path_names_the_fix(self, tmp_path: Path, capsys) -> None:
        blocker = tmp_path / "file"
        blocker.write_text("x", encoding="utf-8")
        code = collect.main(
            ["--project", "a", "--out", str(blocker / "e.json")], runner=FakeRunner()
        )
        assert code == 2 and "writable --out" in capsys.readouterr().err

    def test_missing_gcloud_exits_3(self, tmp_path: Path, capsys, monkeypatch) -> None:
        def no_gcloud(_argv):
            raise wrapper.GcloudNotFound("gcloud was not found on PATH. Install it.")

        code = collect.main(["--project", "a", "--out", str(tmp_path / "e.json")], runner=no_gcloud)
        assert code == 3 and "gcloud was not found" in capsys.readouterr().err

    def test_a_non_read_only_battery_call_is_a_loud_internal_error(self) -> None:
        c = collect.Collector(FakeRunner())
        with pytest.raises(RuntimeError, match="not read-only"):
            c.call("x", "project", "p", ["projects", "delete", "p"])


def test_scripts_are_executable_and_have_shebangs() -> None:
    for name in ("gcloud_readonly.py", "gcp_collect.py", "gcp_analyze.py"):
        path = SCRIPTS / name
        assert path.read_text(encoding="utf-8").startswith("#!/usr/bin/env python3"), name
        assert path.stat().st_mode & 0o111, name
