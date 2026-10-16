"""Tests for the offline analyzer: one positive and one negative case for each rule."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

SKILL = Path(__file__).resolve().parents[2] / "plugins/secure-build/skills/gcp-review"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


analyze = load(SKILL / "scripts/gcp_analyze.py", "gcp_review_analyze_under_test")
rules = sys.modules["gcp_rules"]
collect = load(SKILL / "scripts/gcp_collect.py", "gcp_review_collect_for_analyze_test")
MAP = SKILL / "references/cis-gcp-map.json"

DEFAULT_SA = "123456-compute@developer.gserviceaccount.com"
NOW = "2026-10-16T00:00:00+00:00"


def call(
    kind: str,
    data: Any = None,
    *,
    scope="project",
    target="acme",
    key="",
    status="ok",
    text=None,
    error=None,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "scope": scope,
        "target": target,
        "key": key,
        "argv": [],
        "status": status,
        "data": data,
        "text": text,
        "error": error,
    }


def build(
    *calls: dict[str, Any],
    orgs=(),
    folders=(),
    projects=("acme",),
    edition=None,
    age=90,
    map_path=None,
) -> dict[str, Any]:
    doc = {
        "schema": "gcp-review-evidence/1",
        "collected_at": NOW,
        "scopes": {
            "projects": list(projects),
            "organizations": list(orgs),
            "folders": list(folders),
        },
        "calls": list(calls),
    }
    return analyze.build_document(rules.Evidence(doc), age, map_path, edition)


def found(doc: dict[str, Any], rule: str) -> list[dict[str, Any]]:
    return [f for f in doc["findings"] if f["rule"] == rule]


def policy(*bindings: tuple[str, str], audit: list | None = None) -> dict[str, Any]:
    doc: dict[str, Any] = {"bindings": [{"role": r, "members": [m]} for r, m in bindings]}
    if audit is not None:
        doc["auditConfigs"] = audit
    return doc


FULL_AUDIT = [
    {
        "service": "allServices",
        "auditLogConfigs": [{"logType": "DATA_READ"}, {"logType": "DATA_WRITE"}],
    }
]


def iam(*bindings: tuple[str, str], **kw) -> dict[str, Any]:
    """An IAM policy call that already has Data Access logs, so only the bindings matter."""
    return call("iam-policy", policy(*bindings, audit=FULL_AUDIT), **kw)


class TestIamRules:
    @pytest.mark.parametrize(
        ("role", "severity"),
        [("roles/owner", "high"), ("roles/editor", "high"), ("roles/viewer", "low")],
    )
    def test_basic_role_on_a_person(self, role: str, severity: str) -> None:
        doc = build(iam((role, "user:ana@example.com")))
        hits = found(doc, "GCP-IAM-001")
        assert len(hits) == 1 and hits[0]["severity"] == severity
        assert "remove-iam-policy-binding" in hits[0]["fix"]["commands"][0]

    def test_basic_role_on_group_and_domain(self) -> None:
        doc = build(
            iam(("roles/editor", "group:eng@example.com"), ("roles/viewer", "domain:example.com"))
        )
        assert len(found(doc, "GCP-IAM-001")) == 2

    def test_narrow_role_is_not_flagged(self) -> None:
        doc = build(iam(("roles/storage.objectViewer", "user:ana@example.com")))
        assert doc["findings"] == []

    def test_conditional_binding_is_labelled(self) -> None:
        data = {
            "bindings": [
                {
                    "role": "roles/editor",
                    "members": ["user:a@b.c"],
                    "condition": {"title": "temp access"},
                }
            ]
        }
        doc = build(call("iam-policy", data))
        assert "conditional binding: temp access" in found(doc, "GCP-IAM-001")[0]["evidence"]

    def test_deleted_members_are_ignored(self) -> None:
        doc = build(iam(("roles/owner", "deleted:user:gone@example.com?uid=1")))
        assert found(doc, "GCP-IAM-001") == []

    def test_basic_role_on_a_service_account(self) -> None:
        doc = build(iam(("roles/owner", "serviceAccount:ci@acme.iam.gserviceaccount.com")))
        assert len(found(doc, "GCP-IAM-002")) == 1

    def test_viewer_on_a_service_account_is_not_flagged(self) -> None:
        doc = build(iam(("roles/viewer", "serviceAccount:ci@acme.iam.gserviceaccount.com")))
        assert doc["findings"] == []

    def test_google_apis_service_agent_is_skipped(self) -> None:
        doc = build(
            iam(("roles/editor", "serviceAccount:123456@cloudservices.gserviceaccount.com"))
        )
        assert doc["findings"] == []

    def test_default_compute_service_account_with_editor(self) -> None:
        doc = build(iam(("roles/editor", f"serviceAccount:{DEFAULT_SA}")))
        assert len(found(doc, "GCP-IAM-006")) == 1 and found(doc, "GCP-IAM-002") == []

    def test_default_compute_service_account_with_a_narrow_role_is_fine(self) -> None:
        doc = build(iam(("roles/logging.logWriter", f"serviceAccount:{DEFAULT_SA}")))
        assert doc["findings"] == []

    @pytest.mark.parametrize("member", ["allUsers", "allAuthenticatedUsers"])
    def test_public_members(self, member: str) -> None:
        doc = build(iam(("roles/storage.objectViewer", member)))
        hits = found(doc, "GCP-IAM-003")
        assert len(hits) == 1 and hits[0]["severity"] == "critical"

    def test_service_account_user_for_a_person_is_medium(self) -> None:
        doc = build(iam(("roles/iam.serviceAccountTokenCreator", "user:ana@example.com")))
        assert found(doc, "GCP-IAM-007")[0]["severity"] == "medium"

    def test_service_account_user_for_a_service_account_is_low(self) -> None:
        doc = build(
            iam(("roles/iam.serviceAccountUser", "serviceAccount:a@acme.iam.gserviceaccount.com"))
        )
        assert found(doc, "GCP-IAM-007")[0]["severity"] == "low"

    def test_workload_identity_user_at_project_scope_is_not_flagged(self) -> None:
        doc = build(iam(("roles/iam.workloadIdentityUser", "user:ana@example.com")))
        assert found(doc, "GCP-IAM-007") == []

    def test_organization_and_folder_policies_are_checked(self) -> None:
        doc = build(
            iam(("roles/owner", "user:a@b.c"), scope="organization", target="1"),
            iam(("roles/editor", "user:d@e.f"), scope="folder", target="2"),
            projects=(),
            orgs=("1",),
            folders=("2",),
        )
        fixes = {f["scope"]: f["fix"]["commands"][0] for f in found(doc, "GCP-IAM-001")}
        assert fixes["organization:1"].startswith("gcloud organizations remove-iam-policy-binding")
        assert fixes["folder:2"].startswith(
            "gcloud resource-manager folders remove-iam-policy-binding"
        )

    def test_unsafe_member_text_is_quoted_in_drafts(self) -> None:
        doc = build(iam(("roles/editor", "user:a b;rm -rf@example.com")))
        assert "'user:a b;rm -rf@example.com'" in found(doc, "GCP-IAM-001")[0]["fix"]["commands"][0]


class TestServiceAccountKeys:
    def keys(self, *keys: dict[str, Any]) -> dict[str, Any]:
        return call("sa-keys", list(keys), key="ci@acme.iam.gserviceaccount.com")

    def key(self, created: str, **extra: Any) -> dict[str, Any]:
        return {
            "name": "projects/acme/serviceAccounts/ci@acme/keys/abc123",
            "keyType": "USER_MANAGED",
            "validAfterTime": created,
            **extra,
        }

    def test_old_key_is_a_rotation_finding(self) -> None:
        doc = build(self.keys(self.key("2026-01-01T00:00:00Z")))
        hit = found(doc, "GCP-IAM-005")[0]
        assert hit["severity"] == "high" and "288 days" in hit["evidence"]
        assert "keys disable abc123" in hit["fix"]["commands"][0]
        assert found(doc, "GCP-IAM-004") == []

    def test_recent_key_is_reported_as_existing(self) -> None:
        doc = build(self.keys(self.key("2026-10-01T00:00:00Z")))
        assert len(found(doc, "GCP-IAM-004")) == 1 and found(doc, "GCP-IAM-005") == []

    def test_age_limit_is_configurable(self) -> None:
        recent = self.keys(self.key("2026-09-01T00:00:00Z"))
        assert found(build(recent, age=90), "GCP-IAM-005") == []
        assert len(found(build(recent, age=30), "GCP-IAM-005")) == 1

    def test_system_managed_keys_are_skipped(self) -> None:
        doc = build(self.keys(self.key("2020-01-01T00:00:00Z", keyType="SYSTEM_MANAGED")))
        assert doc["findings"] == []

    def test_disabled_old_key_is_low(self) -> None:
        doc = build(self.keys(self.key("2020-01-01T00:00:00Z", disabled=True)))
        assert found(doc, "GCP-IAM-004")[0]["severity"] == "low"

    def test_key_without_a_timestamp_is_still_reported(self) -> None:
        doc = build(self.keys({"name": "projects/acme/serviceAccounts/x/keys/k1"}))
        assert "creation time not in output" in found(doc, "GCP-IAM-004")[0]["evidence"]

    def test_no_keys_no_findings(self) -> None:
        assert build(self.keys()).get("findings") == []

    def test_impersonation_grants_on_a_service_account(self) -> None:
        pol = policy(
            ("roles/iam.serviceAccountTokenCreator", "allUsers"),
            ("roles/iam.serviceAccountUser", "user:ana@example.com"),
            ("roles/iam.workloadIdentityUser", "principalSet://iam.googleapis.com/x"),
            ("roles/iam.serviceAccountUser", "serviceAccount:b@acme.iam.gserviceaccount.com"),
        )
        doc = build(call("sa-iam-policy", pol, key="ci@acme.iam.gserviceaccount.com"))
        severities = sorted(f["severity"] for f in found(doc, "GCP-IAM-008"))
        assert severities == ["critical", "low"]

    def test_unrelated_sa_policy_roles_are_ignored(self) -> None:
        pol = policy(("roles/viewer", "user:ana@example.com"))
        assert build(call("sa-iam-policy", pol, key="ci@x")).get("findings") == []


def org_calls(
    check: str, *, scope="project", target="acme", **per_name: Any
) -> list[dict[str, Any]]:
    """One org-policy call per constraint name of a check. per_name maps name -> data or status."""
    out = []
    for name in collect.ORG_POLICY_CONSTRAINTS[check]:
        value = per_name.get(name.replace(".", "_"))
        if isinstance(value, str):
            out.append(
                call(
                    "org-policy",
                    scope=scope,
                    target=target,
                    key=f"{check}|{name}",
                    status=value,
                    error=value,
                )
            )
        else:
            data = value if value is not None else {"name": name, "spec": {"rules": []}}
            out.append(call("org-policy", data, scope=scope, target=target, key=f"{check}|{name}"))
    return out


ENFORCED = {"spec": {"rules": [{"enforce": True}]}}


class TestOrgPolicies:
    @pytest.mark.parametrize("check", sorted(collect.ORG_POLICY_CONSTRAINTS))
    def test_unset_constraint_is_a_finding(self, check: str) -> None:
        doc = build(*org_calls(check))
        rule = rules.ORG_CHECKS[check][0]
        hits = found(doc, rule)
        assert len(hits) == 1
        assert hits[0]["fix"]["terraform"].startswith('resource "google_org_policy_policy"')
        assert "gcloud org-policies set-policy policy.yaml" in hits[0]["fix"]["commands"]

    @pytest.mark.parametrize("check", sorted(collect.ORG_POLICY_CONSTRAINTS))
    def test_enforced_under_any_listed_name_is_clean(self, check: str) -> None:
        for name in collect.ORG_POLICY_CONSTRAINTS[check]:
            doc = build(*org_calls(check, **{name.replace(".", "_"): ENFORCED}))
            assert found(doc, rules.ORG_CHECKS[check][0]) == [], name

    def test_unreadable_policy_is_a_gap_not_a_finding(self) -> None:
        calls = org_calls(
            "sa-key-creation",
            iam_disableServiceAccountKeyCreation="denied",
            iam_managed_disableServiceAccountKeyCreation="not-found",
        )
        doc = build(*calls)
        assert found(doc, "GCP-ORG-001") == []
        assert any("iam.disableServiceAccountKeyCreation" in g["what"] for g in doc["gaps"])

    def test_one_readable_unset_name_still_gives_a_finding(self) -> None:
        calls = org_calls(
            "sa-key-creation", iam_managed_disableServiceAccountKeyCreation="not-found"
        )
        assert len(found(build(*calls), "GCP-ORG-001")) == 1

    def test_conditional_only_policy_is_a_gap(self) -> None:
        data = {"spec": {"rules": [{"enforce": True, "condition": {"expression": "x"}}]}}
        calls = org_calls(
            "os-login", compute_requireOsLogin=data, compute_managed_requireOsLogin="not-found"
        )
        doc = build(*calls)
        assert found(doc, "GCP-ORG-006") == []
        assert any("conditional" in g["detail"] for g in doc["gaps"])

    def test_list_constraint_with_allowed_values_counts_as_set(self) -> None:
        data = {"spec": {"rules": [{"values": {"allowedValues": ["is:C0123"]}}]}}
        doc = build(*org_calls("domain-restricted-sharing", iam_allowedPolicyMemberDomains=data))
        assert found(doc, "GCP-ORG-003") == []

    def test_allow_all_does_not_count_as_set(self) -> None:
        data = {"spec": {"rules": [{"allowAll": True}]}}
        doc = build(*org_calls("vm-external-ip", compute_vmExternalIpAccess=data))
        assert len(found(doc, "GCP-ORG-007")) == 1

    def test_deny_all_counts_as_set(self) -> None:
        data = {"spec": {"rules": [{"denyAll": True}]}}
        doc = build(*org_calls("vm-external-ip", compute_vmExternalIpAccess=data))
        assert found(doc, "GCP-ORG-007") == []

    def test_organization_scope_is_checked_with_its_own_parent(self) -> None:
        doc = build(
            *org_calls("sa-key-creation", scope="organization", target="1"),
            projects=(),
            orgs=("1",),
        )
        tf = found(doc, "GCP-ORG-001")[0]["fix"]["terraform"]
        assert 'parent = "organizations/1"' in tf and "iam.disableServiceAccountKeyCreation" in tf

    def test_domain_sharing_draft_names_the_placeholder(self) -> None:
        doc = build(*org_calls("domain-restricted-sharing"))
        assert "DIRECTORY_CUSTOMER_ID" in found(doc, "GCP-ORG-003")[0]["fix"]["terraform"]


class TestAuditLogs:
    def test_missing_audit_config_is_a_finding(self) -> None:
        doc = build(call("iam-policy", policy(("roles/viewer", "group:a@b.c"))))
        hit = found(doc, "GCP-LOG-001")[0]
        assert "no auditConfigs" in hit["evidence"] and "inheritance is unknown" in hit["evidence"]
        assert any("set-iam-policy" in c for c in hit["fix"]["commands"])

    def test_full_data_access_config_is_clean(self) -> None:
        doc = build(call("iam-policy", policy(audit=FULL_AUDIT)))
        assert found(doc, "GCP-LOG-001") == []

    def test_partial_config_names_what_exists(self) -> None:
        audit = [
            {"service": "allServices", "auditLogConfigs": [{"logType": "ADMIN_READ"}]},
            {"service": "storage.googleapis.com", "auditLogConfigs": [{"logType": "DATA_READ"}]},
        ]
        doc = build(call("iam-policy", policy(audit=audit)))
        assert "storage.googleapis.com" in found(doc, "GCP-LOG-001")[0]["evidence"]

    def test_organization_level_config_covers_projects(self) -> None:
        doc = build(
            call("iam-policy", policy(audit=FULL_AUDIT), scope="organization", target="1"),
            call("iam-policy", policy()),
            orgs=("1",),
        )
        assert found(doc, "GCP-LOG-001") == []

    def test_organization_without_config_is_a_finding(self) -> None:
        doc = build(
            call("iam-policy", policy(), scope="organization", target="1"), projects=(), orgs=("1",)
        )
        assert found(doc, "GCP-LOG-001")[0]["scope"] == "organization:1"


def services(*names: str) -> dict[str, Any]:
    return call("services-enabled", [{"config": {"name": n}, "state": "ENABLED"} for n in names])


class TestServices:
    def test_cloud_asset_api_missing(self) -> None:
        assert len(found(build(services("run.googleapis.com")), "GCP-LOG-002")) == 1

    def test_cloud_asset_api_present(self) -> None:
        assert found(build(services("cloudasset.googleapis.com")), "GCP-LOG-002") == []

    def test_container_scanning_missing_with_docker_repos(self) -> None:
        repos = call(
            "ar-repos", [{"name": "projects/acme/locations/us/repositories/r", "format": "DOCKER"}]
        )
        doc = build(services("cloudasset.googleapis.com"), repos)
        assert len(found(doc, "GCP-AR-002")) == 1

    def test_container_scanning_enabled(self) -> None:
        repos = call(
            "ar-repos", [{"name": "projects/acme/locations/us/repositories/r", "format": "DOCKER"}]
        )
        doc = build(
            services("cloudasset.googleapis.com", "containerscanning.googleapis.com"), repos
        )
        assert found(doc, "GCP-AR-002") == []

    def test_no_docker_repos_means_no_scanning_finding(self) -> None:
        repos = call(
            "ar-repos", [{"name": "projects/acme/locations/us/repositories/r", "format": "MAVEN"}]
        )
        assert found(build(services("cloudasset.googleapis.com"), repos), "GCP-AR-002") == []

    def test_unreadable_services_list_makes_no_finding(self) -> None:
        doc = build(call("services-enabled", status="denied", error="PERMISSION_DENIED"))
        assert found(doc, "GCP-LOG-002") == []
        assert any(g["what"].startswith("services-enabled") for g in doc["gaps"])


class TestNetwork:
    def rule(
        self, name="allow-ssh", sources=("0.0.0.0/0",), allowed=None, **extra
    ) -> dict[str, Any]:
        return {
            "name": name,
            "direction": "INGRESS",
            "sourceRanges": list(sources),
            "allowed": allowed or [{"IPProtocol": "tcp", "ports": ["22"]}],
            **extra,
        }

    def test_default_network(self) -> None:
        assert len(found(build(call("networks", [{"name": "default"}])), "GCP-NET-001")) == 1
        assert found(build(call("networks", [{"name": "prod"}])), "GCP-NET-001") == []

    def test_ssh_from_the_internet(self) -> None:
        doc = build(call("firewall-rules", [self.rule()]))
        assert len(found(doc, "GCP-NET-002")) == 1 and found(doc, "GCP-NET-003") == []
        assert "35.235.240.0/20" in found(doc, "GCP-NET-002")[0]["fix"]["commands"][0]

    def test_rdp_from_the_internet(self) -> None:
        rule = self.rule("allow-rdp", allowed=[{"IPProtocol": "tcp", "ports": ["3389"]}])
        doc = build(call("firewall-rules", [rule]))
        assert len(found(doc, "GCP-NET-003")) == 1 and found(doc, "GCP-NET-002") == []

    def test_port_range_and_all_protocols_cover_both(self) -> None:
        wide = self.rule("wide", allowed=[{"IPProtocol": "tcp", "ports": ["20-4000"]}])
        every = self.rule("every", allowed=[{"IPProtocol": "all"}])
        doc = build(call("firewall-rules", [wide, every]))
        assert len(found(doc, "GCP-NET-002")) == 2 and len(found(doc, "GCP-NET-003")) == 2

    def test_tcp_without_ports_means_every_port(self) -> None:
        doc = build(call("firewall-rules", [self.rule(allowed=[{"IPProtocol": "tcp"}])]))
        assert len(found(doc, "GCP-NET-002")) == 1

    @pytest.mark.parametrize(
        "rule",
        [
            {"sources": ("10.0.0.0/8",)},
            {"allowed": [{"IPProtocol": "tcp", "ports": ["443"]}]},
            {"allowed": [{"IPProtocol": "udp", "ports": ["22"]}]},
            {"disabled": True},
            {"direction": "EGRESS"},
        ],
    )
    def test_safe_rules_are_not_flagged(self, rule: dict[str, Any]) -> None:
        sources = rule.pop("sources", ("0.0.0.0/0",))
        doc = build(call("firewall-rules", [self.rule(sources=sources, **rule)]))
        assert found(doc, "GCP-NET-002") == [] and found(doc, "GCP-NET-003") == []


def instance(name="vm1", email=DEFAULT_SA, scopes=None, nat=None, **extra) -> dict[str, Any]:
    inst: dict[str, Any] = {
        "name": name,
        "zone": "zones/us-central1-a",
        "serviceAccounts": [{"email": email, "scopes": scopes or []}],
        "networkInterfaces": [{"accessConfigs": [{"natIP": nat}] if nat else []}],
        **extra,
    }
    return inst


class TestInstances:
    def test_default_service_account(self) -> None:
        doc = build(call("instances", [instance()]))
        assert len(found(doc, "GCP-GCE-001")) == 1 and found(doc, "GCP-GCE-002") == []

    def test_default_service_account_with_full_scope(self) -> None:
        scope = "https://www.googleapis.com/auth/cloud-platform"
        doc = build(call("instances", [instance(scopes=[scope])]))
        assert len(found(doc, "GCP-GCE-002")) == 1 and found(doc, "GCP-GCE-001") == []

    def test_dedicated_service_account_is_fine(self) -> None:
        doc = build(call("instances", [instance(email="app@acme.iam.gserviceaccount.com")]))
        assert doc["findings"] == []

    def test_external_ip(self) -> None:
        doc = build(
            call("instances", [instance(email="app@acme.iam.gserviceaccount.com", nat="34.1.2.3")])
        )
        assert "34.1.2.3" in found(doc, "GCP-GCE-003")[0]["evidence"]

    def test_gke_nodes_are_skipped(self) -> None:
        nodes = [
            instance(name="gke-c-pool-1", nat="34.1.2.3"),
            instance(name="node", labels={"goog-gke-node": ""}, nat="34.1.2.4"),
        ]
        assert build(call("instances", nodes))["findings"] == []

    def info(self, value: str | None) -> dict[str, Any]:
        items = [] if value is None else [{"key": "enable-oslogin", "value": value}]
        return call("project-info", {"commonInstanceMetadata": {"items": items}})

    def test_os_login_missing_from_metadata(self) -> None:
        assert len(found(build(self.info(None)), "GCP-GCE-004")) == 1
        assert len(found(build(self.info("FALSE")), "GCP-GCE-004")) == 1

    def test_os_login_enabled_in_metadata(self) -> None:
        assert found(build(self.info("TRUE")), "GCP-GCE-004") == []

    def test_os_login_enforced_by_org_policy_suppresses_the_finding(self) -> None:
        policy_calls = org_calls("os-login", compute_requireOsLogin=ENFORCED)
        assert found(build(self.info(None), *policy_calls), "GCP-GCE-004") == []


class TestStorageAndSql:
    def bucket(
        self, name="b1", ubla=True, pap="enforced", kms="projects/p/keys/k"
    ) -> dict[str, Any]:
        out: dict[str, Any] = {
            "name": name,
            "iamConfiguration": {"uniformBucketLevelAccess": {"enabled": ubla}},
        }
        if pap:
            out["iamConfiguration"]["publicAccessPrevention"] = pap
        if kms:
            out["encryption"] = {"defaultKmsKeyName": kms}
        return out

    def test_good_bucket_is_clean(self) -> None:
        assert build(call("buckets", [self.bucket()]))["findings"] == []

    def test_bucket_without_uniform_access(self) -> None:
        doc = build(call("buckets", [self.bucket(ubla=False)]))
        assert len(found(doc, "GCP-STO-001")) == 1

    def test_buckets_without_public_access_prevention_and_cmek_are_aggregated(self) -> None:
        buckets = [self.bucket(f"b{i}", pap=None, kms=None) for i in range(12)]
        doc = build(call("buckets", buckets))
        assert len(found(doc, "GCP-STO-002")) == 1 and len(found(doc, "GCP-STO-003")) == 1
        assert "12 resource(s)" in found(doc, "GCP-STO-002")[0]["resource"]
        assert "and 2 more" in found(doc, "GCP-STO-002")[0]["resource"]

    def test_snake_case_keys_are_accepted(self) -> None:
        bucket = {
            "name": "b",
            "uniform_bucket_level_access": False,
            "public_access_prevention": "enforced",
            "default_kms_key": "k",
        }
        doc = build(call("buckets", [bucket]))
        assert len(found(doc, "GCP-STO-001")) == 1 and found(doc, "GCP-STO-002") == []

    def sql(self, public=False, networks=(), kms="k") -> dict[str, Any]:
        out: dict[str, Any] = {
            "name": "db1",
            "settings": {
                "ipConfiguration": {
                    "ipv4Enabled": public,
                    "authorizedNetworks": [{"value": n} for n in networks],
                }
            },
        }
        if kms:
            out["diskEncryptionConfiguration"] = {"kmsKeyName": kms}
        return out

    def test_private_sql_with_cmek_is_clean(self) -> None:
        assert build(call("sql-instances", [self.sql()]))["findings"] == []

    def test_public_ip(self) -> None:
        assert len(found(build(call("sql-instances", [self.sql(public=True)])), "GCP-SQL-001")) == 1

    def test_open_authorized_network_is_critical(self) -> None:
        doc = build(call("sql-instances", [self.sql(public=True, networks=["0.0.0.0/0"])]))
        assert found(doc, "GCP-SQL-003")[0]["severity"] == "critical"

    def test_specific_authorized_network_is_not_open(self) -> None:
        doc = build(call("sql-instances", [self.sql(public=True, networks=["203.0.113.4/32"])]))
        assert found(doc, "GCP-SQL-003") == []

    def test_missing_cmek_is_info(self) -> None:
        doc = build(call("sql-instances", [self.sql(kms=None)]))
        assert found(doc, "GCP-SQL-002")[0]["severity"] == "info"


def service(
    name="web",
    region="us-east1",
    ingress=None,
    invoker_off=None,
    sa="app@acme.iam.gserviceaccount.com",
):
    annotations = {}
    if ingress:
        annotations["run.googleapis.com/ingress"] = ingress
    if invoker_off:
        annotations["run.googleapis.com/invoker-iam-disabled"] = invoker_off
    return {
        "metadata": {
            "name": name,
            "annotations": annotations,
            "labels": {"cloud.googleapis.com/location": region},
        },
        "spec": {"template": {"spec": {"serviceAccountName": sa}}},
    }


class TestCloudRun:
    GOOD = {"ingress": "internal-and-cloud-load-balancing"}

    def test_clean_service(self) -> None:
        assert build(call("run-services", [service(**self.GOOD)]))["findings"] == []

    def test_public_invoker_binding(self) -> None:
        doc = build(
            call("run-services", [service(**self.GOOD)]),
            call("run-iam-policy", policy(("roles/run.invoker", "allUsers")), key="us-east1/web"),
        )
        assert len(found(doc, "GCP-RUN-001")) == 1

    def test_invoker_for_a_service_account_is_fine(self) -> None:
        doc = build(
            call("run-services", [service(**self.GOOD)]),
            call(
                "run-iam-policy",
                policy(("roles/run.invoker", "serviceAccount:a@b.c")),
                key="us-east1/web",
            ),
        )
        assert found(doc, "GCP-RUN-001") == []

    def test_invoker_check_disabled(self) -> None:
        doc = build(call("run-services", [service(invoker_off="true", **self.GOOD)]))
        assert len(found(doc, "GCP-RUN-002")) == 1

    def test_invoker_check_left_on(self) -> None:
        doc = build(call("run-services", [service(invoker_off="false", **self.GOOD)]))
        assert found(doc, "GCP-RUN-002") == []

    def test_ingress_all_or_unset(self) -> None:
        assert len(found(build(call("run-services", [service()])), "GCP-RUN-003")) == 1
        assert len(found(build(call("run-services", [service(ingress="all")])), "GCP-RUN-003")) == 1
        assert (
            found(build(call("run-services", [service(ingress="internal")])), "GCP-RUN-003") == []
        )

    def test_default_service_account(self) -> None:
        for sa in (DEFAULT_SA, None):
            doc = build(call("run-services", [service(sa=sa, **self.GOOD)]))
            assert len(found(doc, "GCP-RUN-004")) == 1


def cluster(**over: Any) -> dict[str, Any]:
    base = {
        "name": "c1",
        "location": "us-central1",
        "privateClusterConfig": {"enablePrivateNodes": True, "enablePrivateEndpoint": True},
        "workloadIdentityConfig": {"workloadPool": "acme.svc.id.goog"},
        "shieldedNodes": {"enabled": True},
        "networkPolicy": {"enabled": True},
        "releaseChannel": {"channel": "REGULAR"},
        "binaryAuthorization": {"evaluationMode": "PROJECT_SINGLETON_POLICY_ENFORCE"},
        "legacyAbac": {},
        "masterAuthorizedNetworksConfig": {"enabled": True},
    }
    base.update(over)
    return base


class TestGke:
    def run(self, **over: Any) -> dict[str, Any]:
        return build(call("clusters", [cluster(**over)]))

    def test_hardened_cluster_is_clean(self) -> None:
        assert self.run()["findings"] == []

    def test_public_nodes(self) -> None:
        doc = self.run(
            privateClusterConfig={"enablePrivateNodes": False, "enablePrivateEndpoint": True}
        )
        assert len(found(doc, "GCP-GKE-001")) == 1

    def test_public_endpoint_without_authorized_networks(self) -> None:
        doc = self.run(
            privateClusterConfig={"enablePrivateNodes": True},
            masterAuthorizedNetworksConfig={"enabled": False},
        )
        assert len(found(doc, "GCP-GKE-002")) == 1

    def test_public_endpoint_with_authorized_networks_is_fine(self) -> None:
        doc = self.run(privateClusterConfig={"enablePrivateNodes": True})
        assert found(doc, "GCP-GKE-002") == []

    def test_no_workload_identity(self) -> None:
        assert len(found(self.run(workloadIdentityConfig={}), "GCP-GKE-003")) == 1

    def test_no_shielded_nodes(self) -> None:
        assert len(found(self.run(shieldedNodes={"enabled": False}), "GCP-GKE-004")) == 1

    def test_network_policy_missing(self) -> None:
        assert len(found(self.run(networkPolicy={}), "GCP-GKE-005")) == 1

    def test_dataplane_v2_counts_as_network_policy(self) -> None:
        doc = self.run(networkPolicy={}, networkConfig={"datapathProvider": "ADVANCED_DATAPATH"})
        assert found(doc, "GCP-GKE-005") == []

    def test_no_release_channel(self) -> None:
        assert len(found(self.run(releaseChannel={}), "GCP-GKE-006")) == 1
        assert len(found(self.run(releaseChannel={"channel": "UNSPECIFIED"}), "GCP-GKE-006")) == 1

    def test_binary_authorization_off(self) -> None:
        assert (
            len(found(self.run(binaryAuthorization={"evaluationMode": "DISABLED"}), "GCP-GKE-007"))
            == 1
        )
        assert len(found(self.run(binaryAuthorization=None), "GCP-GKE-007")) == 1

    def test_binary_authorization_legacy_enabled_flag(self) -> None:
        assert found(self.run(binaryAuthorization={"enabled": True}), "GCP-GKE-007") == []

    def test_legacy_abac(self) -> None:
        assert len(found(self.run(legacyAbac={"enabled": True}), "GCP-GKE-008")) == 1

    def test_autopilot_skips_the_checks_it_sets_itself(self) -> None:
        doc = self.run(
            autopilot={"enabled": True},
            workloadIdentityConfig={},
            shieldedNodes={},
            networkPolicy={},
        )
        for rule in ("GCP-GKE-003", "GCP-GKE-004", "GCP-GKE-005"):
            assert found(doc, rule) == []

    def test_fix_commands_name_the_cluster_and_location(self) -> None:
        cmd = found(self.run(legacyAbac={"enabled": True}), "GCP-GKE-008")[0]["fix"]["commands"][0]
        assert "clusters update c1" in cmd and "--location=us-central1" in cmd


def provider(
    name="gh", condition=None, issuer="https://token.actions.githubusercontent.com", **extra
):
    out: dict[str, Any] = {
        "name": f"projects/1/locations/global/workloadIdentityPools/ci/providers/{name}",
        "state": "ACTIVE",
        "oidc": {"issuerUri": issuer},
        **extra,
    }
    if condition is not None:
        out["attributeCondition"] = condition
    return out


class TestWorkloadIdentityFederation:
    def run(self, *providers: dict[str, Any]) -> dict[str, Any]:
        return build(call("wif-providers", list(providers), key="ci"))

    @pytest.mark.parametrize("condition", [None, "", "  ", "true"])
    def test_missing_condition(self, condition) -> None:
        doc = self.run(provider(condition=condition))
        assert len(found(doc, "GCP-WIF-001")) == 1

    def test_github_condition_naming_the_owner_is_clean(self) -> None:
        assert self.run(provider(condition="assertion.repository_owner=='acme'"))["findings"] == []

    def test_github_condition_naming_only_the_subject_is_flagged(self) -> None:
        doc = self.run(provider(condition="assertion.sub.startsWith('repo:acme/')"))
        assert len(found(doc, "GCP-WIF-002")) == 1 and found(doc, "GCP-WIF-001") == []

    def test_github_issuer_with_trailing_slash_is_recognised(self) -> None:
        doc = self.run(
            provider(
                issuer="https://token.actions.githubusercontent.com/",
                condition="assertion.ref=='refs/heads/main'",
            )
        )
        assert len(found(doc, "GCP-WIF-002")) == 1

    def test_gitlab_condition_naming_the_group_is_clean(self) -> None:
        doc = self.run(
            provider(issuer="https://gitlab.com", condition="assertion.namespace_id=='42'")
        )
        assert doc["findings"] == []

    def test_gitlab_condition_without_a_group_claim_is_flagged(self) -> None:
        doc = self.run(
            provider(issuer="https://gitlab.com", condition="assertion.user_login=='ana'")
        )
        assert "GitLab SaaS" in found(doc, "GCP-WIF-002")[0]["evidence"]

    def test_other_issuers_need_only_a_condition(self) -> None:
        doc = self.run(provider(issuer="https://gitlab.example.com", condition="assertion.x=='y'"))
        assert doc["findings"] == []

    def test_aws_provider_without_condition(self) -> None:
        aws = {
            "name": "projects/1/locations/global/workloadIdentityPools/ci/providers/aws",
            "state": "ACTIVE",
            "aws": {"accountId": "1"},
        }
        assert len(found(self.run(aws), "GCP-WIF-001")) == 1

    def test_deleted_providers_are_ignored(self) -> None:
        assert self.run(provider(state="DELETED"))["findings"] == []

    def test_draft_names_the_pool_and_an_example(self) -> None:
        cmd = found(self.run(provider()), "GCP-WIF-001")[0]["fix"]
        assert "--workload-identity-pool=ci" in cmd["commands"][0]
        assert "repository_owner" in cmd["note"]


class TestPerimetersAndBinaryAuthorization:
    def test_no_access_policy(self) -> None:
        doc = build(
            call("vpcsc-policies", [], scope="organization", target="1"), projects=(), orgs=("1",)
        )
        assert len(found(doc, "GCP-VPCSC-001")) == 1

    def test_policy_without_perimeters(self) -> None:
        doc = build(
            call(
                "vpcsc-policies", [{"name": "accessPolicies/9"}], scope="organization", target="1"
            ),
            call("vpcsc-perimeters", [], scope="organization", target="1", key="9"),
            projects=(),
            orgs=("1",),
        )
        assert "no perimeters" in found(doc, "GCP-VPCSC-001")[0]["evidence"]

    def test_perimeter_with_resources_is_clean(self) -> None:
        per = {
            "name": "accessPolicies/9/servicePerimeters/p",
            "status": {"resources": ["projects/1"]},
        }
        doc = build(
            call(
                "vpcsc-policies", [{"name": "accessPolicies/9"}], scope="organization", target="1"
            ),
            call("vpcsc-perimeters", [per], scope="organization", target="1", key="9"),
            projects=(),
            orgs=("1",),
        )
        assert doc["findings"] == []

    def test_empty_perimeter(self) -> None:
        per = {"name": "accessPolicies/9/servicePerimeters/p", "status": {}}
        doc = build(
            call(
                "vpcsc-policies", [{"name": "accessPolicies/9"}], scope="organization", target="1"
            ),
            call("vpcsc-perimeters", [per], scope="organization", target="1", key="9"),
            projects=(),
            orgs=("1",),
        )
        assert len(found(doc, "GCP-VPCSC-002")) == 1

    def test_unreadable_access_policies_make_no_finding(self) -> None:
        doc = build(
            call("vpcsc-policies", status="denied", scope="organization", target="1"),
            projects=(),
            orgs=("1",),
        )
        assert found(doc, "GCP-VPCSC-001") == []

    def binauthz(self, text: str) -> dict[str, Any]:
        return call("binauthz-policy", None, text=text)

    def rule(self, enforcement: str, evaluation: str) -> str:
        return (
            "defaultAdmissionRule:\n"
            f"  enforcementMode: {enforcement}\n"
            f"  evaluationMode: {evaluation}\n"
        )

    def test_always_allow_default_rule_in_yaml(self) -> None:
        text = self.rule("ENFORCED_BLOCK_AND_AUDIT_LOG", "ALWAYS_ALLOW")
        assert len(found(build(self.binauthz(text)), "GCP-BINAUTHZ-001")) == 1

    def test_dry_run_default_rule_in_yaml(self) -> None:
        text = self.rule("DRYRUN_AUDIT_LOG_ONLY", "REQUIRE_ATTESTATION")
        assert len(found(build(self.binauthz(text)), "GCP-BINAUTHZ-002")) == 1

    def test_enforcing_default_rule_is_clean(self) -> None:
        text = self.rule("ENFORCED_BLOCK_AND_AUDIT_LOG", "REQUIRE_ATTESTATION")
        assert build(self.binauthz(text))["findings"] == []

    def test_json_policy_is_understood(self) -> None:
        data = {"defaultAdmissionRule": {"evaluationMode": "ALWAYS_ALLOW"}}
        assert len(found(build(call("binauthz-policy", data)), "GCP-BINAUTHZ-001")) == 1

    def test_unrecognised_text_gives_no_finding(self) -> None:
        assert build(self.binauthz("something else"))["findings"] == []


REPO = "projects/acme/locations/us/repositories/imgs"


def repo(**over: Any) -> dict[str, Any]:
    base = {
        "name": REPO,
        "format": "DOCKER",
        "kmsKeyName": "k",
        "cleanupPolicies": {"keep": {}},
        "dockerConfig": {"immutableTags": True},
        "vulnerabilityScanningConfig": {
            "enablementConfig": "INHERITED",
            "enablementState": "SCANNING_ACTIVE",
        },
    }
    base.update(over)
    return base


class TestArtifactRegistry:
    def test_hardened_repository_is_clean(self) -> None:
        doc = build(
            services("cloudasset.googleapis.com", "containerscanning.googleapis.com"),
            call("ar-repos", [repo()]),
        )
        assert doc["findings"] == []

    def test_public_repository(self) -> None:
        doc = build(
            call("ar-repos", [repo()]),
            call("ar-iam-policy", policy(("roles/artifactregistry.reader", "allUsers")), key=REPO),
        )
        hit = found(doc, "GCP-AR-001")[0]
        assert hit["severity"] == "critical" and "--location=us" in hit["fix"]["commands"][0]

    def test_private_repository_policy_is_clean(self) -> None:
        pol = policy(("roles/artifactregistry.reader", "serviceAccount:a@b.c"))
        doc = build(call("ar-repos", [repo()]), call("ar-iam-policy", pol, key=REPO))
        assert found(doc, "GCP-AR-001") == []

    @pytest.mark.parametrize(
        "scan",
        [{"enablementConfig": "DISABLED"}, {"enablementState": "SCANNING_DISABLED"}],
    )
    def test_scanning_disabled(self, scan: dict[str, str]) -> None:
        doc = build(call("ar-repos", [repo(vulnerabilityScanningConfig=scan)]))
        assert len(found(doc, "GCP-AR-003")) == 1

    def test_scanning_setting_missing_from_output_is_a_gap(self) -> None:
        doc = build(call("ar-repos", [repo(vulnerabilityScanningConfig=None)]))
        assert found(doc, "GCP-AR-003") == []
        assert any("vulnerability scanning setting" in g["what"] for g in doc["gaps"])

    def test_mutable_tags_cleanup_and_cmek(self) -> None:
        bare = repo(dockerConfig={}, cleanupPolicies=None, kmsKeyName=None)
        doc = build(call("ar-repos", [bare]))
        assert len(found(doc, "GCP-AR-004")) == len(found(doc, "GCP-AR-005")) == 1
        assert len(found(doc, "GCP-AR-006")) == 1

    def test_immutable_tags_do_not_apply_to_non_docker_repositories(self) -> None:
        doc = build(call("ar-repos", [repo(format="MAVEN", dockerConfig={})]))
        assert found(doc, "GCP-AR-004") == []


class TestAssuredWorkloads:
    def workloads(self, *items: dict[str, Any]) -> dict[str, Any]:
        return call("assured-workloads", list(items), scope="organization", target="1", key="us")

    WORKLOAD = {
        "name": "organizations/1/locations/us/workloads/w1",
        "displayName": "gov",
        "complianceRegime": "FEDRAMP_MODERATE",
        "resources": [{"resourceId": 555, "resourceType": "CONSUMER_FOLDER"}],
    }

    def run(self, *extra: dict[str, Any], ancestors=None) -> dict[str, Any]:
        anc = call(
            "ancestors", ancestors if ancestors is not None else [{"id": "555", "type": "folder"}]
        )
        return build(self.workloads(self.WORKLOAD), anc, *extra, orgs=("1",))

    def test_workload_is_recorded_without_a_compliance_claim(self) -> None:
        hit = found(self.run(), "GCP-AW-001")[0]
        assert "FEDRAMP_MODERATE" in hit["evidence"]
        assert "does not show that the regime is met" in hit["evidence"]

    def test_project_under_the_workload_folder_has_no_outside_finding(self) -> None:
        assert found(self.run(), "GCP-AW-003") == []

    def test_project_outside_any_workload_folder(self) -> None:
        doc = self.run(ancestors=[{"id": "999", "type": "folder"}])
        assert len(found(doc, "GCP-AW-003")) == 1

    def test_unresolved_violations(self) -> None:
        violations = call(
            "assured-violations",
            [
                {"state": "UNRESOLVED", "category": "RESOURCE_LOCATION"},
                {"state": "RESOLVED", "category": "OTHER"},
            ],
            scope="organization",
            target="1",
            key=self.WORKLOAD["name"],
        )
        hit = found(self.run(violations), "GCP-AW-002")[0]
        assert "1 unresolved" in hit["evidence"] and "RESOURCE_LOCATION" in hit["evidence"]

    def test_only_resolved_violations_make_no_finding(self) -> None:
        violations = call(
            "assured-violations", [{"state": "RESOLVED"}], scope="organization", target="1", key="w"
        )
        assert found(self.run(violations), "GCP-AW-002") == []

    def test_failed_listing_is_a_gap_and_no_outside_finding(self) -> None:
        failed = call(
            "assured-workloads",
            status="denied",
            scope="organization",
            target="1",
            key="us",
            error="PERMISSION_DENIED",
        )
        doc = build(failed, call("ancestors", [{"id": "1"}]), orgs=("1",))
        assert found(doc, "GCP-AW-003") == []
        assert any(g["what"].startswith("assured-workloads") for g in doc["gaps"])


class TestGaps:
    def test_failed_calls_become_gaps(self) -> None:
        doc = build(call("clusters", status="not-enabled", error="API not enabled"))
        gap = next(g for g in doc["gaps"] if g["what"].startswith("clusters"))
        assert gap["status"] == "not-enabled" and "API not enabled" in gap["detail"]

    def test_missing_organization_scope_is_reported(self) -> None:
        doc = build()
        assert any(g["status"] == "not-collected" for g in doc["gaps"])
        assert not any(g["status"] == "not-collected" for g in build(orgs=("1",))["gaps"])

    def test_individual_org_policy_failures_are_not_listed_twice(self) -> None:
        calls = org_calls("serial-port", compute_disableSerialPortAccess="not-found")
        doc = build(*calls)
        assert [g for g in doc["gaps"] if g["status"] == "not-found"] == []

    def test_not_covered_areas_are_always_listed(self) -> None:
        assert any("BigQuery" in item for item in build()["not_covered"])


class TestBenchmarkMap:
    def test_ids_are_attached_when_the_map_loads(self) -> None:
        doc = build(call("iam-policy", policy()), map_path=MAP)
        assert doc["benchmark"]["edition"] == "5.0.0"
        hit = found(doc, "GCP-LOG-001")[0]
        assert hit["benchmark"][0]["id"] == "2.1"
        assert "Confirm each ID" in doc["benchmark"]["notice"]

    def test_a_different_edition_drops_the_ids(self) -> None:
        doc = build(call("iam-policy", policy()), map_path=MAP, edition="6.0.0")
        assert found(doc, "GCP-LOG-001")[0]["benchmark"] == []
        assert "numbering changes" in doc["benchmark"]["notice"]

    def test_missing_map_file_is_stated(self, tmp_path: Path) -> None:
        doc = build(call("iam-policy", policy()), map_path=tmp_path / "nope.json")
        assert "No benchmark map" in doc["benchmark"]["notice"]

    def test_unreadable_map_file_is_stated(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("{", encoding="utf-8")
        assert "unreadable" in build(map_path=bad)["benchmark"]["notice"]

    def test_every_mapped_rule_exists_and_every_entry_is_complete(self) -> None:
        data = json.loads(MAP.read_text(encoding="utf-8"))
        assert data["verified_against"] and data["edition"] and data["standard"]
        for rule, entries in data["rules"].items():
            assert rule in rules.RULES, rule
            for entry in entries:
                assert entry["id"] and entry["title"], rule

    def test_rules_without_a_verified_id_carry_none(self) -> None:
        doc = build(iam(("roles/editor", "user:a@b.c")), map_path=MAP)
        assert found(doc, "GCP-IAM-001")[0]["benchmark"] == []


class TestOutput:
    def evidence_doc(self) -> dict[str, Any]:
        return build(
            iam(("roles/owner", "user:ana@example.com"), ("roles/viewer", "allUsers")),
            call("clusters", status="denied", error="PERMISSION_DENIED"),
            call("identity", None, scope="global", target="gcloud", text="ana@example.com\n"),
        )

    def test_findings_are_sorted_by_severity_and_numbered(self) -> None:
        doc = self.evidence_doc()
        order = [f["severity"] for f in doc["findings"]]
        assert order == sorted(order, key=rules.SEVERITIES.index)
        assert [f["id"] for f in doc["findings"]] == ["F-001", "F-002"]

    def test_output_is_deterministic(self) -> None:
        assert self.evidence_doc() == self.evidence_doc()

    def test_each_finding_has_the_documented_fields(self) -> None:
        for f in self.evidence_doc()["findings"]:
            assert {
                "id",
                "rule",
                "severity",
                "title",
                "scope",
                "resource",
                "evidence",
                "benchmark",
                "fix",
            } <= set(f)
            assert f["severity"] in rules.SEVERITIES

    def test_summary_counts_match(self) -> None:
        doc = self.evidence_doc()
        assert doc["summary"]["by_severity"]["critical"] == 1
        assert sum(doc["summary"]["by_severity"].values()) == len(doc["findings"])

    def test_markdown_has_the_three_sections_and_the_disclaimer(self) -> None:
        text = analyze.render_markdown(self.evidence_doc())
        for heading in ("## Findings", "## Not checked (gaps)", "## Drafted fixes (not executed)"):
            assert heading in text
        assert "does not state that any project or environment is compliant" in text
        assert "Run as: ana@example.com" in text
        assert "Nothing in this review ran any of these." in text
        assert "```sh" in text

    def test_markdown_for_a_clean_evidence_file(self) -> None:
        doc = build(call("iam-policy", policy(audit=FULL_AUDIT)), orgs=("1",))
        text = analyze.render_markdown(doc)
        assert "No findings from the checks that could run" in text
        assert "No drafted fixes." in text

    def test_the_report_never_calls_anything_authorized(self) -> None:
        text = analyze.render_markdown(self.evidence_doc()).lower()
        assert "fedramp ready" not in text and "authorized to operate" not in text

    def test_analysis_modules_cannot_run_commands(self) -> None:
        for name in ("gcp_rules.py", "gcp_analyze.py"):
            source = (SKILL / "scripts" / name).read_text(encoding="utf-8")
            assert "subprocess" not in source and "os.system" not in source, name


class TestCli:
    def write(self, tmp_path: Path, *calls: dict[str, Any]) -> Path:
        path = tmp_path / "evidence.json"
        doc = {
            "schema": "gcp-review-evidence/1",
            "collected_at": NOW,
            "scopes": {"projects": ["acme"], "organizations": [], "folders": []},
            "calls": list(calls),
        }
        path.write_text(json.dumps(doc), encoding="utf-8")
        return path

    def test_writes_json_and_markdown_to_out_dir(self, tmp_path: Path, capsys) -> None:
        evidence = self.write(tmp_path, iam(("roles/owner", "user:a@b.c")))
        out = tmp_path / "out"
        assert analyze.main([str(evidence), "--out-dir", str(out)]) == 0
        data = json.loads((out / "findings.json").read_text(encoding="utf-8"))
        assert data["schema"] == "gcp-review-findings/1" and len(data["findings"]) == 1
        assert "## Findings" in (out / "report.md").read_text(encoding="utf-8")
        assert "1 findings" in capsys.readouterr().out

    def test_prints_markdown_by_default(self, tmp_path: Path, capsys) -> None:
        assert analyze.main([str(self.write(tmp_path))]) == 0
        assert "## Drafted fixes (not executed)" in capsys.readouterr().out

    def test_json_only(self, tmp_path: Path, capsys) -> None:
        assert analyze.main([str(self.write(tmp_path)), "--format", "json"]) == 0
        assert json.loads(capsys.readouterr().out)["schema"] == "gcp-review-findings/1"

    def test_fail_on_threshold(self, tmp_path: Path) -> None:
        evidence = self.write(tmp_path, iam(("roles/viewer", "user:a@b.c")))
        assert analyze.main([str(evidence), "--format", "json", "--fail-on", "low"]) == 1
        assert analyze.main([str(evidence), "--format", "json", "--fail-on", "high"]) == 0

    def test_missing_evidence_file_names_the_fix(self, tmp_path: Path, capsys) -> None:
        assert analyze.main([str(tmp_path / "nope.json")]) == 2
        assert "gcp_collect.py" in capsys.readouterr().err

    def test_wrong_schema_is_rejected(self, tmp_path: Path, capsys) -> None:
        path = tmp_path / "x.json"
        path.write_text('{"schema": "other"}', encoding="utf-8")
        assert analyze.main([str(path)]) == 2
        assert "not a gcp-review-evidence/1 document" in capsys.readouterr().err

    def test_invalid_json_and_missing_calls_are_rejected(self, tmp_path: Path, capsys) -> None:
        path = tmp_path / "x.json"
        path.write_text("{", encoding="utf-8")
        assert analyze.main([str(path)]) == 2
        path.write_text('{"schema": "gcp-review-evidence/1"}', encoding="utf-8")
        assert analyze.main([str(path)]) == 2
        assert "no 'calls' list" in capsys.readouterr().err

    def test_list_document_is_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "x.json"
        path.write_text("[]", encoding="utf-8")
        assert analyze.main([str(path)]) == 2

    def test_bad_key_age_is_rejected(self, tmp_path: Path, capsys) -> None:
        assert analyze.main([str(self.write(tmp_path)), "--key-max-age-days", "0"]) == 2
        assert "at least 1" in capsys.readouterr().err

    def test_unwritable_out_dir_names_the_fix(self, tmp_path: Path, capsys) -> None:
        blocker = tmp_path / "file"
        blocker.write_text("x", encoding="utf-8")
        code = analyze.main([str(self.write(tmp_path)), "--out-dir", str(blocker / "sub")])
        assert code == 2 and "writable --out-dir" in capsys.readouterr().err

    def test_collect_then_analyze_round_trip(self, tmp_path: Path) -> None:
        class Runner:
            def __call__(self, argv):
                if argv[:2] == ["projects", "get-iam-policy"]:
                    return collect.CallResult("ok", data=policy(("roles/owner", "user:a@b.c")))
                return collect.CallResult("ok", data=[])

        out = tmp_path / "evidence.json"
        assert collect.main(["--project", "acme", "--out", str(out)], runner=Runner()) == 0
        assert analyze.main([str(out), "--format", "json", "--fail-on", "high"]) == 1
