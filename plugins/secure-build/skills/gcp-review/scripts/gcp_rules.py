#!/usr/bin/env python3
"""Rules for gcp_analyze.py: read an evidence document, produce findings, gaps and draft fixes.

This module is imported by gcp_analyze.py. It does no I/O and never runs a command. Every fix
it produces is text for a person to read and run.
"""

from __future__ import annotations

import json
import re
import shlex
from datetime import UTC, datetime
from typing import Any

SEVERITIES = ["critical", "high", "medium", "low", "info"]
MAX_LISTED = 10  # resources named in one aggregated finding

BASIC_ROLES = {"roles/owner": "high", "roles/editor": "high", "roles/viewer": "low"}
IMPERSONATION_ROLES = {
    "roles/iam.serviceAccountUser",
    "roles/iam.serviceAccountTokenCreator",
    "roles/iam.serviceAccountOpenIdTokenCreator",
    "roles/iam.workloadIdentityUser",
}
BROAD_IMPERSONATION_ROLES = {
    "roles/iam.serviceAccountUser",
    "roles/iam.serviceAccountTokenCreator",
}
PUBLIC_MEMBERS = {"allUsers", "allAuthenticatedUsers"}
DEFAULT_COMPUTE_SA = re.compile(r"^\d+-compute@developer\.gserviceaccount\.com$")
# The Google APIs Service Agent holds Editor by design in many projects; it is skipped.
GOOGLE_APIS_AGENT = re.compile(r"^\d+@cloudservices\.gserviceaccount\.com$")
CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
# Issuer -> (name, claims that scope a token to one owner or project).
ISSUERS = {
    "https://token.actions.githubusercontent.com": (
        "GitHub Actions",
        ("repository_owner", "repository_owner_id", "repository", "repository_id"),
    ),
    "https://gitlab.com": (
        "GitLab SaaS",
        ("namespace_id", "namespace_path", "project_id", "project_path"),
    ),
}
ISSUER_EXAMPLES = {
    "GitHub Actions": "assertion.repository_owner=='YOUR_ORG'",
    "GitLab SaaS": "assertion.namespace_id=='YOUR_GROUP_ID'",
}

# rule id -> (default severity, title)
RULES: dict[str, tuple[str, str]] = {
    "GCP-IAM-001": ("high", "Basic role granted to a person, group or domain"),
    "GCP-IAM-002": ("high", "Basic role granted to a service account"),
    "GCP-IAM-003": ("critical", "Policy grants access to allUsers or allAuthenticatedUsers"),
    "GCP-IAM-004": ("medium", "User-managed service account key exists"),
    "GCP-IAM-005": ("high", "User-managed service account key older than the rotation limit"),
    "GCP-IAM-006": ("high", "Default compute service account holds Editor"),
    "GCP-IAM-007": ("medium", "Service Account User or Token Creator granted at a broad scope"),
    "GCP-IAM-008": ("low", "Impersonation role granted on a service account"),
    "GCP-ORG-001": ("high", "Service account key creation is not blocked by org policy"),
    "GCP-ORG-002": ("medium", "Service account key upload is not blocked by org policy"),
    "GCP-ORG-003": ("medium", "Domain restricted sharing is not enforced"),
    "GCP-ORG-004": ("medium", "Uniform bucket-level access is not required by org policy"),
    "GCP-ORG-005": ("low", "Public access prevention is not required by org policy"),
    "GCP-ORG-006": ("medium", "OS Login is not required by org policy"),
    "GCP-ORG-007": ("medium", "VM external IP access is not restricted by org policy"),
    "GCP-ORG-008": ("low", "Serial port access is not disabled by org policy"),
    "GCP-ORG-009": ("medium", "Cloud SQL public IPs are not restricted by org policy"),
    "GCP-ORG-010": ("low", "CMEK use is not required by org policy"),
    "GCP-LOG-001": ("medium", "Data Access audit logs are not enabled for all services"),
    "GCP-LOG-002": ("low", "Cloud Asset API is not enabled"),
    "GCP-NET-001": ("medium", "Default network exists"),
    "GCP-NET-002": ("high", "Firewall rule allows SSH from the internet"),
    "GCP-NET-003": ("high", "Firewall rule allows RDP from the internet"),
    "GCP-VPCSC-001": ("medium", "No VPC Service Controls perimeter found"),
    "GCP-VPCSC-002": ("low", "Perimeter encloses no resources in its enforced configuration"),
    "GCP-GCE-001": ("medium", "Instance uses the default compute service account"),
    "GCP-GCE-002": ("high", "Instance uses the default service account with full API access"),
    "GCP-GCE-003": ("medium", "Instance has an external IP address"),
    "GCP-GCE-004": ("medium", "OS Login is not enabled in project metadata"),
    "GCP-STO-001": ("medium", "Bucket does not use uniform bucket-level access"),
    "GCP-STO-002": ("low", "Bucket does not enforce public access prevention"),
    "GCP-STO-003": ("info", "Bucket has no customer-managed encryption key"),
    "GCP-SQL-001": ("high", "Cloud SQL instance has a public IP"),
    "GCP-SQL-002": ("info", "Cloud SQL instance has no customer-managed encryption key"),
    "GCP-SQL-003": ("critical", "Cloud SQL instance allows connections from any address"),
    "GCP-RUN-001": ("high", "Cloud Run service grants the invoker role to the public"),
    "GCP-RUN-002": ("high", "Cloud Run service has the invoker IAM check disabled"),
    "GCP-RUN-003": ("low", "Cloud Run service accepts traffic from all sources"),
    "GCP-RUN-004": ("medium", "Cloud Run service runs as the default compute service account"),
    "GCP-GKE-001": ("high", "GKE cluster nodes are not private"),
    "GCP-GKE-002": ("high", "GKE control plane is public with no authorized networks"),
    "GCP-GKE-003": ("medium", "GKE cluster has no Workload Identity pool"),
    "GCP-GKE-004": ("medium", "GKE cluster does not use Shielded nodes"),
    "GCP-GKE-005": ("medium", "GKE cluster has no network policy enforcement"),
    "GCP-GKE-006": ("low", "GKE cluster is not on a release channel"),
    "GCP-GKE-007": ("medium", "GKE cluster does not enforce Binary Authorization"),
    "GCP-GKE-008": ("high", "GKE cluster has legacy ABAC enabled"),
    "GCP-WIF-001": ("high", "Workload identity provider has no attribute condition"),
    "GCP-WIF-002": ("high", "GitHub or GitLab provider condition does not name an owner claim"),
    "GCP-AR-001": ("critical", "Artifact Registry repository is readable by the public"),
    "GCP-AR-002": ("medium", "Container Scanning API is not enabled"),
    "GCP-AR-003": ("medium", "Artifact Registry repository has vulnerability scanning disabled"),
    "GCP-AR-004": ("low", "Docker repository allows tags to be overwritten"),
    "GCP-AR-005": ("info", "Repository has no cleanup policies"),
    "GCP-AR-006": ("info", "Repository has no customer-managed encryption key"),
    "GCP-BINAUTHZ-001": ("medium", "Binary Authorization default rule allows all images"),
    "GCP-BINAUTHZ-002": ("low", "Binary Authorization default rule only logs violations"),
    "GCP-AW-001": ("info", "Assured Workloads workload recorded"),
    "GCP-AW-002": ("medium", "Assured Workloads workload has unresolved violations"),
    "GCP-AW-003": ("info", "Project is not under any listed Assured Workloads folder"),
}

# org policy check (same keys as gcp_collect.ORG_POLICY_CONSTRAINTS) -> rule id, constraint
ORG_CHECKS: dict[str, tuple[str, str]] = {
    "sa-key-creation": ("GCP-ORG-001", "iam.disableServiceAccountKeyCreation"),
    "sa-key-upload": ("GCP-ORG-002", "iam.disableServiceAccountKeyUpload"),
    "domain-restricted-sharing": ("GCP-ORG-003", "iam.allowedPolicyMemberDomains"),
    "uniform-bucket-access": ("GCP-ORG-004", "storage.uniformBucketLevelAccess"),
    "public-access-prevention": ("GCP-ORG-005", "storage.publicAccessPrevention"),
    "os-login": ("GCP-ORG-006", "compute.requireOsLogin"),
    "vm-external-ip": ("GCP-ORG-007", "compute.vmExternalIpAccess"),
    "serial-port": ("GCP-ORG-008", "compute.disableSerialPortAccess"),
    "sql-public-ip": ("GCP-ORG-009", "sql.restrictPublicIp"),
    "cmek-required": ("GCP-ORG-010", "gcp.restrictNonCmekServices"),
}
CMEK_SERVICES = [
    "storage.googleapis.com",
    "sqladmin.googleapis.com",
    "artifactregistry.googleapis.com",
    "bigquery.googleapis.com",
]


# ---------------------------------------------------------------- small helpers


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def short(name: str) -> str:
    return name.rsplit("/", 1)[-1]


def quote(value: str) -> str:
    return shlex.quote(value)


def gc(*words: str, **flags: str) -> str:
    """Build one gcloud command line. Words starting with -- keep their name and quote the value."""
    out = ["gcloud"]
    for word in words:
        if word.startswith("--"):
            name, eq, value = word.partition("=")
            out.append(name + eq + quote(value) if eq else name)
        else:
            out.append(quote(word))
    out += [f"--{k.replace('_', '-')}={quote(v)}" for k, v in flags.items()]
    return " ".join(out)


def truthy(value: Any) -> bool:
    return value is True or (isinstance(value, str) and value.strip().lower() == "true")


def dig(obj: Any, *path: str) -> Any:
    for part in path:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(part)
    return obj


def dicts(data: Any) -> list[dict[str, Any]]:
    return [d for d in data if isinstance(d, dict)] if isinstance(data, list) else []


def first(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def binding_rows(policy: Any):
    for binding in dicts(dig(policy, "bindings")):
        for member in binding.get("members") or []:
            yield binding.get("role", ""), member, binding.get("condition")


def cond_note(condition: Any) -> str:
    if isinstance(condition, dict) and condition:
        return f" (conditional binding: {condition.get('title') or condition.get('expression')})"
    return ""


def parent_path(scope: str, target: str) -> str:
    return {"project": "projects", "folder": "folders", "organization": "organizations"}[
        scope
    ] + f"/{target}"


def remove_binding(scope: str, target: str, member: str, role: str) -> str:
    words = {
        "project": ("projects",),
        "organization": ("organizations",),
        "folder": ("resource-manager", "folders"),
    }[scope]
    return gc(*words, "remove-iam-policy-binding", target, member=member, role=role)


# ---------------------------------------------------------------- evidence and report


class Evidence:
    def __init__(self, doc: dict[str, Any]) -> None:
        self.doc = doc
        self.calls: list[dict[str, Any]] = doc["calls"]
        self.collected_at = parse_time(doc.get("collected_at")) or datetime.now(UTC)

    def select(self, kind: str, scope: str | None = None, target: str | None = None):
        for call in self.calls:
            if call.get("kind") != kind:
                continue
            if scope is not None and call.get("scope") != scope:
                continue
            if target is not None and call.get("target") != target:
                continue
            yield call

    def ok_data(self, kind: str, scope: str, target: str) -> Any:
        for call in self.select(kind, scope, target):
            if call.get("status") == "ok":
                return call.get("data")
        return None

    def targets(self, scope: str) -> list[str]:
        key = {"project": "projects", "organization": "organizations", "folder": "folders"}[scope]
        return list((self.doc.get("scopes") or {}).get(key) or [])


class Report:
    def __init__(self, evidence: Evidence, key_max_age_days: int) -> None:
        self.evidence = evidence
        self.key_max_age_days = key_max_age_days
        self.findings: list[dict[str, Any]] = []
        self.gaps: list[dict[str, str]] = []
        self._seen: set[tuple[str, str, str]] = set()

    def add(
        self,
        rule: str,
        scope: str,
        resource: str,
        evidence: str,
        cmds: list[str] | None = None,
        note: str | None = None,
        tf: str | None = None,
        sev: str | None = None,
    ) -> None:
        key = (rule, scope, resource)
        if key in self._seen:
            return
        self._seen.add(key)
        default_severity, title = RULES[rule]
        has_fix = bool(cmds or tf or note)
        self.findings.append(
            {
                "rule": rule,
                "severity": sev or default_severity,
                "title": title,
                "scope": scope,
                "resource": resource,
                "evidence": evidence[:400],
                "benchmark": [],
                "fix": {"commands": cmds or [], "terraform": tf, "note": note} if has_fix else None,
            }
        )

    def aggregate(
        self,
        rule: str,
        scope: str,
        names: list[str],
        evidence: str,
        cmds: list[str] | None = None,
        note: str | None = None,
    ) -> None:
        if not names:
            return
        names = sorted(names)
        more = f" and {len(names) - MAX_LISTED} more" if len(names) > MAX_LISTED else ""
        listed = ", ".join(names[:MAX_LISTED])
        self.add(rule, scope, f"{len(names)} resource(s): {listed}{more}", evidence, cmds, note)

    def gap(self, what: str, status: str, detail: str = "") -> None:
        entry = {"what": what, "status": status, "detail": detail[:240]}
        if entry not in self.gaps:
            self.gaps.append(entry)


# ---------------------------------------------------------------- IAM


def check_iam_policies(rep: Report) -> None:
    for call in rep.evidence.select("iam-policy"):
        if call.get("status") != "ok":
            continue
        scope, target = call["scope"], call["target"]
        label = f"{scope}:{target}"
        for role, member, condition in binding_rows(call.get("data")):
            where = f"{scope} {target}: {role} -> {member}{cond_note(condition)}"
            resource = f"{role} -> {member}"
            cmds = [remove_binding(scope, target, member, role)]
            note = (
                "Grant a narrower role first if the member still needs access, then remove this "
                "binding. Check audit logs for the member's recent use before removing it."
            )
            if member in PUBLIC_MEMBERS:
                rep.add("GCP-IAM-003", label, resource, where, cmds, note)
            elif role in BROAD_IMPERSONATION_ROLES:
                sev = "low" if member.startswith("serviceAccount:") else None
                rep.add("GCP-IAM-007", label, resource, where, cmds, note, sev=sev)
            elif role in BASIC_ROLES and not member.startswith("deleted:"):
                _basic_role_finding(rep, label, resource, where, member, role, cmds, note)


def _basic_role_finding(
    rep: Report,
    label: str,
    resource: str,
    where: str,
    member: str,
    role: str,
    cmds: list[str],
    note: str,
) -> None:
    email = member.split(":", 1)[-1]
    if not member.startswith("serviceAccount:"):
        rep.add("GCP-IAM-001", label, resource, where, cmds, note, sev=BASIC_ROLES[role])
    elif GOOGLE_APIS_AGENT.match(email) or role == "roles/viewer":
        return
    elif DEFAULT_COMPUTE_SA.match(email) and role == "roles/editor":
        rep.add("GCP-IAM-006", label, resource, where, cmds, note)
    else:
        rep.add("GCP-IAM-002", label, resource, where, cmds, note)


def check_service_account_keys(rep: Report) -> None:
    now = rep.evidence.collected_at
    for call in rep.evidence.select("sa-keys"):
        if call.get("status") != "ok":
            continue
        label, email = f"project:{call['target']}", call.get("key", "")
        for key in dicts(call.get("data")):
            if key.get("keyType") not in (None, "USER_MANAGED"):
                continue
            key_id = short(key.get("name", "unknown"))
            created = parse_time(key.get("validAfterTime"))
            disabled = truthy(key.get("disabled"))
            age = (now - created).days if created else None
            cmds = [
                gc("iam", "service-accounts", "keys", "disable", key_id, iam_account=email),
                "# after confirming nothing breaks, delete it:",
                "# " + gc("iam", "service-accounts", "keys", "delete", key_id, iam_account=email),
            ]
            note = (
                "Disable first and watch for failures, then delete. Replace the key with "
                "Workload Identity Federation or an attached service account where possible."
            )
            resource = f"key {key_id} of {email}"
            if age is not None and age > rep.key_max_age_days and not disabled:
                text = (
                    f"created {key.get('validAfterTime')} ({age} days before collection); "
                    f"limit {rep.key_max_age_days} days"
                )
                rep.add("GCP-IAM-005", label, resource, text, cmds, note)
            else:
                created_text = key.get("validAfterTime") or "creation time not in output"
                text = f"created {created_text}" + ("; key is disabled" if disabled else "")
                sev = "low" if disabled else None
                rep.add("GCP-IAM-004", label, resource, text, cmds, note, sev=sev)


def check_service_account_policies(rep: Report) -> None:
    for call in rep.evidence.select("sa-iam-policy"):
        if call.get("status") != "ok":
            continue
        email, label, project = call.get("key", ""), f"project:{call['target']}", call["target"]
        for role, member, condition in binding_rows(call.get("data")):
            if role not in IMPERSONATION_ROLES:
                continue
            kind = member.split(":", 1)[0]
            if member not in PUBLIC_MEMBERS and kind not in {"user", "group", "domain"}:
                continue
            where = f"{role} -> {member} on {email}{cond_note(condition)}"
            cmds = [
                gc(
                    "iam",
                    "service-accounts",
                    "remove-iam-policy-binding",
                    email,
                    member=member,
                    role=role,
                    project=project,
                )
            ]
            sev = "critical" if member in PUBLIC_MEMBERS else None
            note = None if sev else "Review whether this person needs to act as the account."
            rep.add(
                "GCP-IAM-008", label, f"{role} -> {member} on {email}", where, cmds, note, sev=sev
            )


# ---------------------------------------------------------------- org policy and logging


def policy_state(call: dict[str, Any]) -> tuple[str, str]:
    """Return (enforced | not-enforced | unknown, reason) for one effective policy call."""
    if call.get("status") != "ok" or not isinstance(call.get("data"), dict):
        return "unknown", str(call.get("status"))
    rules = dig(call["data"], "spec", "rules")
    rules = [r for r in rules if isinstance(r, dict)] if isinstance(rules, list) else []
    if not rules:
        return "not-enforced", "no rules in the effective policy"
    unconditional = [r for r in rules if not r.get("condition")]
    for rule in unconditional:
        values = rule.get("values") if isinstance(rule.get("values"), dict) else {}
        if (
            truthy(rule.get("enforce"))
            or truthy(rule.get("denyAll"))
            or values.get("allowedValues")
            or values.get("deniedValues")
        ):
            return "enforced", "policy rule present"
    if not unconditional:
        return "unknown", "only conditional rules; evaluate by hand"
    return "not-enforced", "rules do not enforce the constraint"


def org_policy_fix(check: str, constraint: str, scope: str, target: str):
    """Return (commands, terraform, note) that enforce one constraint."""
    parent = parent_path(scope, target)
    if check == "domain-restricted-sharing":
        body = 'values {\n      allowed_values = ["DIRECTORY_CUSTOMER_ID"]\n    }'
        yaml_rule = ["  - values:", "      allowedValues:", "      - DIRECTORY_CUSTOMER_ID"]
        note = "Replace DIRECTORY_CUSTOMER_ID with your Cloud Identity customer ID (starts with C)."
    elif check == "vm-external-ip":
        body = 'deny_all = "TRUE"'
        yaml_rule = ["  - denyAll: true"]
        note = "Deny all, or list the instances that need an external IP in allowed_values."
    elif check == "cmek-required":
        quoted = ", ".join(f'"{s}"' for s in CMEK_SERVICES)
        body = f"values {{\n      denied_values = [{quoted}]\n    }}"
        yaml_rule = ["  - values:", "      deniedValues:", *[f"      - {s}" for s in CMEK_SERVICES]]
        note = "Check the CMEK org policy page for the current value format before applying."
    else:
        body = 'enforce = "TRUE"'
        yaml_rule = ["  - enforce: true"]
        note = "Test in a folder or project first; a new org policy can block existing workflows."
    label = re.sub(r"[^a-z0-9_]", "_", check.lower())
    terraform = (
        f'resource "google_org_policy_policy" "{label}" {{\n'
        f'  name   = "{parent}/policies/{constraint}"\n'
        f'  parent = "{parent}"\n\n'
        f"  spec {{\n    rules {{\n      {body}\n    }}\n  }}\n}}"
    )
    yaml_lines = [f"name: {parent}/policies/{constraint}", "spec:", "  rules:", *yaml_rule]
    commands = [
        "cat > policy.yaml <<'EOF'\n" + "\n".join(yaml_lines) + "\nEOF",
        "gcloud org-policies set-policy policy.yaml",
    ]
    return commands, terraform, note


def check_org_policies(rep: Report) -> None:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for call in rep.evidence.select("org-policy"):
        check = str(call.get("key", "")).split("|", 1)[0]
        groups.setdefault((call["scope"], call["target"], check), []).append(call)
    for (scope, target, check), calls in sorted(groups.items()):
        if check not in ORG_CHECKS:
            continue
        rule, constraint = ORG_CHECKS[check]
        states = [(c, *policy_state(c)) for c in calls]
        if any(state == "enforced" for _, state, _ in states):
            continue
        label = f"{scope}:{target}"
        names = [(str(c.get("key", "")).split("|", 1)[-1], s, why) for c, s, why in states]
        if any(state == "not-enforced" for _, state, _ in states):
            seen = "; ".join(f"{n}: {s} ({why})" for n, s, why in names)
            cmds, tf, note = org_policy_fix(check, constraint, scope, target)
            rep.add(rule, label, f"constraints/{constraint}", seen, cmds, note, tf)
        else:
            detail = "; ".join(f"{n}: {why}" for n, _, why in names)
            rep.gap(f"org policy {constraint} at {label}", "unknown", detail)


def full_data_access(policy: Any) -> tuple[bool, list[str]]:
    """Return (allServices logs DATA_READ and DATA_WRITE, services with any audit config)."""
    configs = dicts(dig(policy, "auditConfigs"))
    services = sorted(str(c.get("service")) for c in configs)
    for cfg in configs:
        if cfg.get("service") != "allServices":
            continue
        log_types = {c.get("logType") for c in dicts(cfg.get("auditLogConfigs"))}
        if {"DATA_READ", "DATA_WRITE"} <= log_types:
            return True, services
    return False, services


AUDIT_BLOCK = [
    "auditConfigs:",
    "- service: allServices",
    "  auditLogConfigs:",
    "  - logType: ADMIN_READ",
    "  - logType: DATA_READ",
    "  - logType: DATA_WRITE",
]


def check_audit_logs(rep: Report) -> None:
    calls = [c for c in rep.evidence.select("iam-policy") if c.get("status") == "ok"]
    inherited = any(
        c["scope"] in {"organization", "folder"} and full_data_access(c.get("data"))[0]
        for c in calls
    )
    org_collected = bool(rep.evidence.targets("organization"))
    for call in calls:
        scope, target = call["scope"], call["target"]
        if scope == "folder":
            continue
        full, services = full_data_access(call.get("data"))
        if full or (scope == "project" and inherited):
            continue
        present = ", ".join(services) if services else "no auditConfigs in the policy"
        if scope == "project" and not org_collected:
            present += (
                "; organization and folder policies were not collected, so inheritance is unknown"
            )
        words = ("projects",) if scope == "project" else ("organizations",)
        hint = "# edit policy.yaml and merge this block:\n" + "\n".join(
            f"# {x}" for x in AUDIT_BLOCK
        )
        cmds = [
            gc(*words, "get-iam-policy", target, "--format=yaml") + " > policy.yaml",
            hint,
            gc(*words, "set-iam-policy", target, "policy.yaml"),
        ]
        note = (
            "Data Access logs add cost and volume. Review exemptions and log retention with the "
            "logging owner before applying the change."
        )
        rep.add(
            "GCP-LOG-001",
            f"{scope}:{target}",
            f"{scope} {target}",
            f"auditConfigs present for: {present}",
            cmds,
            note,
        )


def enabled_services(data: Any) -> set[str]:
    names: set[str] = set()
    for item in dicts(data):
        name = dig(item, "config", "name") or short(str(item.get("name", "")))
        if name:
            names.add(str(name))
    return names


def check_services(rep: Report) -> None:
    for project in rep.evidence.targets("project"):
        enabled_data = rep.evidence.ok_data("services-enabled", "project", project)
        if enabled_data is None:
            continue
        enabled = enabled_services(enabled_data)
        label = f"project:{project}"
        if "cloudasset.googleapis.com" not in enabled:
            rep.add(
                "GCP-LOG-002",
                label,
                f"project {project}",
                "cloudasset.googleapis.com is not enabled",
                [gc("services", "enable", "cloudasset.googleapis.com", project=project)],
                "Enabling an API can add cost; confirm with the project owner.",
            )
        repos = dicts(rep.evidence.ok_data("ar-repos", "project", project))
        if any(str(r.get("format", "")).upper() == "DOCKER" for r in repos) and (
            "containerscanning.googleapis.com" not in enabled
        ):
            rep.add(
                "GCP-AR-002",
                label,
                f"project {project}",
                "Docker repositories exist and containerscanning.googleapis.com is not enabled",
                [gc("services", "enable", "containerscanning.googleapis.com", project=project)],
                "Scanning is billed per image scanned; check current pricing first.",
            )


# ---------------------------------------------------------------- network and compute


def covers_port(allowed: Any, port: int) -> bool:
    for entry in dicts(allowed):
        proto = str(entry.get("IPProtocol", entry.get("ipProtocol", ""))).lower()
        if proto == "all":
            return True
        if proto != "tcp":
            continue
        ports = entry.get("ports")
        if not ports:
            return True
        for spec in ports:
            low, _, high = str(spec).partition("-")
            try:
                if int(low) <= port <= int(high or low):
                    return True
            except ValueError:
                continue
    return False


def check_network(rep: Report) -> None:
    for project in rep.evidence.targets("project"):
        label = f"project:{project}"
        for net in dicts(rep.evidence.ok_data("networks", "project", project)):
            if net.get("name") == "default":
                rep.add(
                    "GCP-NET-001",
                    label,
                    "network default",
                    "a network named 'default' exists",
                    [gc("compute", "networks", "delete", "default", project=project)],
                    "Delete only after moving workloads off it and removing its firewall rules. "
                    "Set the skip-default-network org policy for new projects.",
                )
        for rule in dicts(rep.evidence.ok_data("firewall-rules", "project", project)):
            if rule.get("direction", "INGRESS") != "INGRESS" or truthy(rule.get("disabled")):
                continue
            sources = set(rule.get("sourceRanges") or [])
            if not sources & {"0.0.0.0/0", "::/0"}:
                continue
            name = str(rule.get("name", "unknown"))
            text = f"sourceRanges {sorted(sources)}; allowed {json.dumps(rule.get('allowed'))}"
            cmd = gc(
                "compute",
                "firewall-rules",
                "update",
                name,
                "--source-ranges=35.235.240.0/20",
                project=project,
            )
            note = (
                "35.235.240.0/20 is the range Identity-Aware Proxy uses for TCP forwarding. "
                "Confirm it in the IAP docs, then use IAP instead of open SSH or RDP."
            )
            for port, rule_id in ((22, "GCP-NET-002"), (3389, "GCP-NET-003")):
                if covers_port(rule.get("allowed"), port):
                    rep.add(rule_id, label, f"firewall rule {name}", text, [cmd], note)


def is_gke_node(instance: dict[str, Any]) -> bool:
    labels = instance.get("labels") if isinstance(instance.get("labels"), dict) else {}
    return "goog-gke-node" in labels or str(instance.get("name", "")).startswith("gke-")


def check_instances(rep: Report) -> None:
    for project in rep.evidence.targets("project"):
        label = f"project:{project}"
        for inst in dicts(rep.evidence.ok_data("instances", "project", project)):
            if not is_gke_node(inst):
                _instance_findings(rep, project, label, inst)
        info = rep.evidence.ok_data("project-info", "project", project)
        if not isinstance(info, dict):
            continue
        items = dicts(dig(info, "commonInstanceMetadata", "items"))
        value = next((str(i.get("value")) for i in items if i.get("key") == "enable-oslogin"), "")
        enforced = any(
            policy_state(c)[0] == "enforced"
            for c in rep.evidence.select("org-policy", "project", project)
            if str(c.get("key", "")).startswith("os-login|")
        )
        if value.upper() != "TRUE" and not enforced:
            rep.add(
                "GCP-GCE-004",
                label,
                f"project {project}",
                "enable-oslogin is not TRUE in common instance metadata",
                [
                    gc(
                        "compute",
                        "project-info",
                        "add-metadata",
                        "--metadata=enable-oslogin=TRUE",
                        project=project,
                    )
                ],
            )


def _instance_findings(rep: Report, project: str, label: str, inst: dict[str, Any]) -> None:
    name, zone = str(inst.get("name", "unknown")), short(str(inst.get("zone", "")))
    resource = f"instance {name}"
    for sa in dicts(inst.get("serviceAccounts")):
        if not DEFAULT_COMPUTE_SA.match(str(sa.get("email", ""))):
            continue
        scopes = sa.get("scopes") or []
        cmd = gc(
            "compute",
            "instances",
            "set-service-account",
            name,
            "--service-account=NEW_SA_EMAIL",
            "--scopes=cloud-platform",
            zone=zone,
            project=project,
        )
        rule = "GCP-GCE-002" if CLOUD_PLATFORM_SCOPE in scopes else "GCP-GCE-001"
        note = (
            "Stop the instance first. Use a dedicated service account with only the roles it needs."
        )
        rep.add(
            rule,
            label,
            resource,
            f"service account {sa.get('email')}; scopes {scopes}",
            [cmd],
            note,
        )
    external = [
        ac.get("natIP", "assigned")
        for ni in dicts(inst.get("networkInterfaces"))
        for ac in dicts(ni.get("accessConfigs"))
    ]
    if external:
        rep.add(
            "GCP-GCE-003",
            label,
            resource,
            f"external IP {external[0]}",
            [gc("compute", "instances", "delete-access-config", name, zone=zone, project=project)],
            "Put the instance behind a load balancer, IAP or Cloud NAT first.",
        )


# ---------------------------------------------------------------- data services


def check_buckets(rep: Report) -> None:
    for project in rep.evidence.targets("project"):
        label = f"project:{project}"
        no_pap: list[str] = []
        no_cmek: list[str] = []
        for bucket in dicts(rep.evidence.ok_data("buckets", "project", project)):
            name = str(bucket.get("name", "unknown"))
            ubla = first(
                dig(bucket, "iamConfiguration", "uniformBucketLevelAccess", "enabled"),
                bucket.get("uniform_bucket_level_access"),
            )
            if ubla is not None and not truthy(ubla):
                rep.add(
                    "GCP-STO-001",
                    label,
                    f"bucket {name}",
                    "uniformBucketLevelAccess.enabled is false",
                    [
                        gc(
                            "storage",
                            "buckets",
                            "update",
                            f"gs://{name}",
                            "--uniform-bucket-level-access",
                        )
                    ],
                    "Check that no workload depends on object ACLs first.",
                )
            pap = first(
                dig(bucket, "iamConfiguration", "publicAccessPrevention"),
                bucket.get("public_access_prevention"),
            )
            if str(pap).lower() != "enforced":
                no_pap.append(name)
            kms = first(
                dig(bucket, "encryption", "defaultKmsKeyName"), bucket.get("default_kms_key")
            )
            if not kms:
                no_cmek.append(name)
        rep.aggregate(
            "GCP-STO-002",
            label,
            no_pap,
            "publicAccessPrevention is not 'enforced'",
            [gc("storage", "buckets", "update", "gs://BUCKET", "--public-access-prevention")],
            "Run once per bucket listed. Check for intentionally public buckets first.",
        )
        rep.aggregate(
            "GCP-STO-003",
            label,
            no_cmek,
            "no encryption.defaultKmsKeyName",
            [gc("storage", "buckets", "update", "gs://BUCKET", "--default-encryption-key=KMS_KEY")],
            "Only needed where policy requires customer-managed keys.",
        )


def check_sql(rep: Report) -> None:
    for project in rep.evidence.targets("project"):
        label = f"project:{project}"
        no_cmek: list[str] = []
        for inst in dicts(rep.evidence.ok_data("sql-instances", "project", project)):
            name = str(inst.get("name", "unknown"))
            ip_cfg = dig(inst, "settings", "ipConfiguration") or {}
            resource = f"Cloud SQL instance {name}"
            if truthy(ip_cfg.get("ipv4Enabled")):
                rep.add(
                    "GCP-SQL-001",
                    label,
                    resource,
                    "ipv4Enabled is true",
                    [gc("sql", "instances", "patch", name, "--no-assign-ip", project=project)],
                    "Configure a private IP first, or connections will fail.",
                )
            for net in dicts(ip_cfg.get("authorizedNetworks")):
                if net.get("value") in {"0.0.0.0/0", "::/0"}:
                    rep.add(
                        "GCP-SQL-003",
                        label,
                        resource,
                        f"authorized network {net.get('value')}",
                        [
                            gc(
                                "sql",
                                "instances",
                                "patch",
                                name,
                                "--clear-authorized-networks",
                                project=project,
                            )
                        ],
                    )
            if not dig(inst, "diskEncryptionConfiguration", "kmsKeyName"):
                no_cmek.append(name)
        rep.aggregate("GCP-SQL-002", label, no_cmek, "no diskEncryptionConfiguration.kmsKeyName")


# ---------------------------------------------------------------- Cloud Run and GKE


def check_cloud_run(rep: Report) -> None:
    for project in rep.evidence.targets("project"):
        policies = {
            c.get("key"): c.get("data")
            for c in rep.evidence.select("run-iam-policy", "project", project)
            if c.get("status") == "ok"
        }
        for service in dicts(rep.evidence.ok_data("run-services", "project", project)):
            meta = service.get("metadata") or {}
            name = str(meta.get("name", "unknown"))
            region = (meta.get("labels") or {}).get("cloud.googleapis.com/location", "")
            _service_findings(rep, project, name, region, service, policies.get(f"{region}/{name}"))


def _service_findings(
    rep: Report, project: str, name: str, region: str, service: dict[str, Any], policy: Any
) -> None:
    label = f"project:{project}"
    resource = f"Cloud Run service {name} ({region})"
    annotations = (service.get("metadata") or {}).get("annotations") or {}
    where = {"region": region, "project": project}
    for role, member, _ in binding_rows(policy):
        if role == "roles/run.invoker" and member in PUBLIC_MEMBERS:
            cmd = gc(
                "run",
                "services",
                "remove-iam-policy-binding",
                name,
                member=member,
                role=role,
                **where,
            )
            note = "Confirm the service is meant to be private. A public service may be intended."
            rep.add("GCP-RUN-001", label, resource, f"{role} -> {member}", [cmd], note)
    if str(annotations.get("run.googleapis.com/invoker-iam-disabled", "")).lower() == "true":
        rep.add(
            "GCP-RUN-002",
            label,
            resource,
            "annotation run.googleapis.com/invoker-iam-disabled is 'true'",
            [gc("run", "services", "update", name, "--invoker-iam-check", **where)],
            "Check the flag name with `gcloud run services update --help`.",
        )
    ingress = annotations.get("run.googleapis.com/ingress", "all")
    if ingress == "all":
        rep.add(
            "GCP-RUN-003",
            label,
            resource,
            f"ingress annotation is {ingress!r} (or unset)",
            [
                gc(
                    "run",
                    "services",
                    "update",
                    name,
                    "--ingress=internal-and-cloud-load-balancing",
                    **where,
                )
            ],
            "Use 'internal' for services only called from inside the network.",
        )
    sa_name = dig(service, "spec", "template", "spec", "serviceAccountName")
    if not sa_name or DEFAULT_COMPUTE_SA.match(str(sa_name)):
        rep.add(
            "GCP-RUN-004",
            label,
            resource,
            f"serviceAccountName is {sa_name or 'unset'}",
            [gc("run", "services", "update", name, "--service-account=NEW_SA_EMAIL", **where)],
            "Create a dedicated service account with only the roles it needs.",
        )


def check_gke(rep: Report) -> None:
    for project in rep.evidence.targets("project"):
        for cluster in dicts(rep.evidence.ok_data("clusters", "project", project)):
            _cluster_findings(rep, project, cluster)


def _cluster_findings(rep: Report, project: str, cluster: dict[str, Any]) -> None:
    name = str(cluster.get("name", "unknown"))
    loc = str(cluster.get("location", cluster.get("zone", "")))
    label, resource = f"project:{project}", f"GKE cluster {name} ({loc})"

    def update(*flags: str) -> list[str]:
        return [gc("container", "clusters", "update", name, *flags, location=loc, project=project)]

    private = truthy(dig(cluster, "privateClusterConfig", "enablePrivateNodes")) or truthy(
        dig(cluster, "networkConfig", "defaultEnablePrivateNodes")
    )
    if not private:
        rep.add(
            "GCP-GKE-001",
            label,
            resource,
            "enablePrivateNodes is not true",
            None,
            "Private nodes usually need a new cluster or node pool; see the GKE private docs.",
        )
    endpoint_private = truthy(dig(cluster, "privateClusterConfig", "enablePrivateEndpoint"))
    if not endpoint_private and not truthy(
        dig(cluster, "masterAuthorizedNetworksConfig", "enabled")
    ):
        rep.add(
            "GCP-GKE-002",
            label,
            resource,
            "public endpoint and masterAuthorizedNetworksConfig.enabled is not true",
            update("--enable-master-authorized-networks", "--master-authorized-networks=CIDR_LIST"),
            "Replace CIDR_LIST with the ranges that must reach the control plane.",
        )
    if not truthy(dig(cluster, "autopilot", "enabled")):
        _standard_cluster_findings(rep, project, cluster, label, resource, update)
    channel = dig(cluster, "releaseChannel", "channel")
    if channel in (None, "", "UNSPECIFIED"):
        rep.add(
            "GCP-GKE-006",
            label,
            resource,
            "releaseChannel.channel is unset",
            update("--release-channel=regular"),
            "Pick the channel your change policy allows.",
        )
    mode = dig(cluster, "binaryAuthorization", "evaluationMode")
    on = truthy(dig(cluster, "binaryAuthorization", "enabled"))
    if not on and mode in (None, "", "DISABLED", "EVALUATION_MODE_UNSPECIFIED"):
        rep.add(
            "GCP-GKE-007",
            label,
            resource,
            f"binaryAuthorization evaluationMode is {mode or 'unset'}",
            update("--binauthz-evaluation-mode=PROJECT_SINGLETON_POLICY_ENFORCE"),
            "Set the project policy first or every deploy will be blocked.",
        )
    if truthy(dig(cluster, "legacyAbac", "enabled")):
        rep.add(
            "GCP-GKE-008",
            label,
            resource,
            "legacyAbac.enabled is true",
            update("--no-enable-legacy-authorization"),
        )


def _standard_cluster_findings(rep, project, cluster, label, resource, update) -> None:
    """Checks that Autopilot clusters skip because Autopilot sets them itself."""
    if not dig(cluster, "workloadIdentityConfig", "workloadPool"):
        rep.add(
            "GCP-GKE-003",
            label,
            resource,
            "workloadIdentityConfig.workloadPool is unset",
            update(f"--workload-pool={project}.svc.id.goog"),
            "Node pools need the GKE metadata server enabled afterwards.",
        )
    if not truthy(dig(cluster, "shieldedNodes", "enabled")):
        rep.add(
            "GCP-GKE-004",
            label,
            resource,
            "shieldedNodes.enabled is not true",
            update("--enable-shielded-nodes"),
        )
    policy_on = truthy(dig(cluster, "networkPolicy", "enabled")) or (
        dig(cluster, "networkConfig", "datapathProvider") == "ADVANCED_DATAPATH"
    )
    if not policy_on:
        rep.add(
            "GCP-GKE-005",
            label,
            resource,
            "networkPolicy.enabled is not true and datapathProvider is not ADVANCED_DATAPATH",
            None,
            "Use Dataplane V2 on a new cluster, or turn on network policy (restarts nodes).",
        )


# ---------------------------------------------------------------- identity federation


def condition_names_claim(condition: str, claims: tuple[str, ...]) -> bool:
    return any(re.search(rf"(assertion|attribute)\.{re.escape(c)}\b", condition) for c in claims)


def check_wif(rep: Report) -> None:
    for call in rep.evidence.select("wif-providers"):
        if call.get("status") != "ok":
            continue
        project, pool = call["target"], call.get("key", "")
        for prov in dicts(call.get("data")):
            if str(prov.get("state", "ACTIVE")).upper() == "DELETED":
                continue
            name = short(str(prov.get("name", "unknown")))
            condition = str(prov.get("attributeCondition") or "").strip()
            issuer = str(dig(prov, "oidc", "issuerUri") or "").rstrip("/")
            known = ISSUERS.get(issuer)
            example = ISSUER_EXAMPLES.get(known[0] if known else "", "assertion.CLAIM=='VALUE'")
            cmd = gc(
                "iam",
                "workload-identity-pools",
                "providers",
                "update-oidc",
                name,
                "--attribute-condition=CONDITION",
                workload_identity_pool=pool,
                location="global",
                project=project,
            )
            note = f"Replace CONDITION, for example: {example}"
            args = (f"project:{project}", f"provider {name} in pool {pool}")
            if not condition or condition.lower() == "true":
                text = f"attributeCondition is empty; issuer {issuer or 'not OIDC'}"
                rep.add("GCP-WIF-001", *args, text, [cmd], note)
            elif known and not condition_names_claim(condition, known[1]):
                claims = ", ".join(known[1])
                text = f"{known[0]} issuer; condition {condition!r} names none of {claims}"
                rep.add("GCP-WIF-002", *args, text, [cmd], note)


# ---------------------------------------------------------------- perimeters, binauthz, registry


def check_vpc_sc(rep: Report) -> None:
    for org in rep.evidence.targets("organization"):
        label = f"organization:{org}"
        policies = rep.evidence.ok_data("vpcsc-policies", "organization", org)
        if policies is None:
            continue
        perimeters = [
            p
            for c in rep.evidence.select("vpcsc-perimeters", "organization", org)
            if c.get("status") == "ok"
            for p in dicts(c.get("data"))
        ]
        if not dicts(policies) or not perimeters:
            text = (
                "no access policy found"
                if not dicts(policies)
                else "access policy has no perimeters"
            )
            note = (
                "Design perimeters with the data owners, test in dry-run mode, then enforce. "
                "See the VPC Service Controls docs."
            )
            rep.add("GCP-VPCSC-001", label, f"organization {org}", text, None, note)
        for perimeter in perimeters:
            if not dig(perimeter, "status", "resources"):
                rep.add(
                    "GCP-VPCSC-002",
                    label,
                    f"perimeter {perimeter.get('name', 'unknown')}",
                    "status.resources is empty (dry-run only or not yet populated)",
                )


def binauthz_default_rule(call: dict[str, Any]) -> tuple[str | None, str | None]:
    """Return (evaluationMode, enforcementMode) of the default admission rule."""
    data, text = call.get("data"), call.get("text") or ""
    if isinstance(data, dict):
        rule = data.get("defaultAdmissionRule") or {}
        return rule.get("evaluationMode"), rule.get("enforcementMode")
    match = re.search(r"^defaultAdmissionRule:\s*\n((?:[ \t]+.*\n?)+)", text, re.MULTILINE)
    block = match.group(1) if match else ""
    evaluation = re.search(r"evaluationMode:\s*(\S+)", block)
    enforcement = re.search(r"enforcementMode:\s*(\S+)", block)
    return (
        evaluation.group(1) if evaluation else None,
        enforcement.group(1) if enforcement else None,
    )


def check_binauthz(rep: Report) -> None:
    for call in rep.evidence.select("binauthz-policy"):
        if call.get("status") != "ok":
            continue
        evaluation, enforcement = binauthz_default_rule(call)
        label, resource = f"project:{call['target']}", f"project {call['target']}"
        if evaluation == "ALWAYS_ALLOW":
            note = (
                "Export the policy, set the default rule to REQUIRE_ATTESTATION with your "
                "attestors and ENFORCED_BLOCK_AND_AUDIT_LOG, test in dry-run, then import it "
                "with `gcloud container binauthz policy import FILE`."
            )
            text = "defaultAdmissionRule.evaluationMode is ALWAYS_ALLOW"
            rep.add("GCP-BINAUTHZ-001", label, resource, text, None, note)
        elif enforcement == "DRYRUN_AUDIT_LOG_ONLY":
            text = "defaultAdmissionRule.enforcementMode is DRYRUN_AUDIT_LOG_ONLY"
            rep.add("GCP-BINAUTHZ-002", label, resource, text)


def check_artifact_registry(rep: Report) -> None:
    for project in rep.evidence.targets("project"):
        label = f"project:{project}"
        no_cleanup: list[str] = []
        no_cmek: list[str] = []
        mutable: list[str] = []
        for repo in dicts(rep.evidence.ok_data("ar-repos", "project", project)):
            name = short(str(repo.get("name", "unknown")))
            is_docker = str(repo.get("format", "")).upper() == "DOCKER"
            _scanning_finding(rep, label, name, repo, is_docker)
            if is_docker and not truthy(dig(repo, "dockerConfig", "immutableTags")):
                mutable.append(name)
            if not repo.get("cleanupPolicies"):
                no_cleanup.append(name)
            if not repo.get("kmsKeyName"):
                no_cmek.append(name)
        immutable_cmd = gc(
            "artifacts",
            "repositories",
            "update",
            "REPOSITORY",
            "--immutable-tags",
            location="LOCATION",
        )
        rep.aggregate(
            "GCP-AR-004",
            label,
            mutable,
            "dockerConfig.immutableTags is not true",
            [immutable_cmd],
            "Run once per repository listed.",
        )
        rep.aggregate("GCP-AR-005", label, no_cleanup, "cleanupPolicies is empty")
        rep.aggregate("GCP-AR-006", label, no_cmek, "kmsKeyName is unset")
        for call in rep.evidence.select("ar-iam-policy", "project", project):
            if call.get("status") == "ok":
                _repo_public_findings(rep, project, label, call)


def _scanning_finding(rep: Report, label: str, name: str, repo: dict, is_docker: bool) -> None:
    scan = repo.get("vulnerabilityScanningConfig")
    if not is_docker:
        return
    if not isinstance(scan, dict):
        rep.gap(
            f"vulnerability scanning setting of repository {name}",
            "unknown",
            "vulnerabilityScanningConfig is not in the list output",
        )
    elif (
        scan.get("enablementConfig") == "DISABLED"
        or scan.get("enablementState") == "SCANNING_DISABLED"
    ):
        note = (
            "Change the repository scanning setting or the project default in Artifact "
            "Registry settings. Check the current gcloud flag first."
        )
        rep.add(
            "GCP-AR-003",
            label,
            f"repository {name}",
            f"vulnerabilityScanningConfig {json.dumps(scan)}",
            None,
            note,
        )


def _repo_public_findings(rep: Report, project: str, label: str, call: dict[str, Any]) -> None:
    full = str(call.get("key", ""))
    name = short(full)
    parts = full.split("/")
    location = parts[3] if len(parts) > 3 else "LOCATION"
    for role, member, _ in binding_rows(call.get("data")):
        if member in PUBLIC_MEMBERS:
            cmd = gc(
                "artifacts",
                "repositories",
                "remove-iam-policy-binding",
                name,
                location=location,
                member=member,
                role=role,
                project=project,
            )
            rep.add("GCP-AR-001", label, f"repository {name}", f"{role} -> {member}", [cmd])


# ---------------------------------------------------------------- assured workloads


def check_assured_workloads(rep: Report) -> None:
    for org in rep.evidence.targets("organization"):
        label = f"organization:{org}"
        listed_ok = False
        workloads: list[dict[str, Any]] = []
        for call in rep.evidence.select("assured-workloads", "organization", org):
            if call.get("status") == "ok":
                listed_ok = True
                workloads += dicts(call.get("data"))
        folder_ids: set[str] = set()
        for workload in workloads:
            for res in dicts(workload.get("resources")):
                if res.get("resourceId") is not None:
                    folder_ids.add(str(res["resourceId"]))
            text = (
                f"displayName {workload.get('displayName')!r}; complianceRegime "
                f"{workload.get('complianceRegime', 'not in output')}. This records configuration "
                "and does not show that the regime is met."
            )
            rep.add("GCP-AW-001", label, f"workload {short(str(workload.get('name', '?')))}", text)
        for call in rep.evidence.select("assured-violations", "organization", org):
            if call.get("status") != "ok":
                continue
            open_items = [v for v in dicts(call.get("data")) if v.get("state") == "UNRESOLVED"]
            if open_items:
                cats = ", ".join(sorted({str(v.get("category", "unknown")) for v in open_items}))
                note = (
                    "Review each violation in the Assured Workloads console or with `gcloud "
                    "assured workloads violations describe`. Acknowledging one is a human decision."
                )
                rep.add(
                    "GCP-AW-002",
                    label,
                    f"workload {short(str(call.get('key', '')))}",
                    f"{len(open_items)} unresolved violation(s); categories: {cats}",
                    None,
                    note,
                )
        if listed_ok:
            for project in rep.evidence.targets("project"):
                ancestors = dicts(rep.evidence.ok_data("ancestors", "project", project))
                if ancestors and not {str(a.get("id")) for a in ancestors} & folder_ids:
                    rep.add(
                        "GCP-AW-003",
                        f"project:{project}",
                        f"project {project}",
                        "no ancestor folder matches a workload resource in the listed locations",
                    )


# ---------------------------------------------------------------- driver


CHECKS = (
    check_iam_policies,
    check_service_account_keys,
    check_service_account_policies,
    check_org_policies,
    check_audit_logs,
    check_services,
    check_network,
    check_instances,
    check_buckets,
    check_sql,
    check_cloud_run,
    check_gke,
    check_wif,
    check_vpc_sc,
    check_binauthz,
    check_artifact_registry,
    check_assured_workloads,
)


def collect_gaps(rep: Report) -> None:
    for call in rep.evidence.calls:
        status = call.get("status")
        if status == "ok" or call.get("kind") == "org-policy":
            continue
        what = f"{call.get('kind')} at {call.get('scope')}:{call.get('target')}"
        if call.get("key"):
            what += f" ({call['key']})"
        rep.gap(what, str(status), str(call.get("error") or call.get("text") or ""))
    if not (rep.evidence.doc.get("scopes") or {}).get("organizations"):
        rep.gap(
            "organization-level IAM, org policies at the organization, VPC Service Controls "
            "and Assured Workloads",
            "not-collected",
            "no --organization was given, so inherited settings are unknown",
        )


def run_checks(rep: Report) -> None:
    for check in CHECKS:
        check(rep)
    collect_gaps(rep)
    rep.findings.sort(
        key=lambda f: (SEVERITIES.index(f["severity"]), f["rule"], f["scope"], f["resource"])
    )
    for number, finding in enumerate(rep.findings, start=1):
        finding["id"] = f"F-{number:03d}"
    rep.gaps.sort(key=lambda g: (g["what"], g["status"]))
