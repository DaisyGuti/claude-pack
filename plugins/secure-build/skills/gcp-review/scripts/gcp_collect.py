#!/usr/bin/env python3
"""Collect read-only GCP configuration evidence into one JSON file.

Usage:
    gcp_collect.py --project PROJECT_ID [--project ...] [--organization ORG_ID]
                   [--folder FOLDER_ID] [--assured-location us] --out evidence.json

Every call goes through gcloud_readonly.validate, so a call that is not on the read-only
allowlist is never run. A call that is denied, needs an API that is not enabled, or fails for
another reason is recorded with a status and the collection continues. The analyzer lists
those as gaps.

Exit codes: 0 evidence written (even if some calls failed), 2 bad arguments, 3 gcloud missing.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = "gcp-review-evidence/1"


def _load_wrapper() -> Any:
    """Load the sibling wrapper by path, so this works from any working directory."""
    name = "gcloud_readonly"
    if name in sys.modules:
        return sys.modules[name]
    path = Path(__file__).resolve().parent / "gcloud_readonly.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}; reinstall the plugin")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


wrapper = _load_wrapper()

# Org policy constraints checked on every scope. Each check lists the legacy name and the
# managed name where Google publishes both; the analyzer treats either one as satisfying it.
# Verify the current names against the constraint reference before relying on this list.
ORG_POLICY_CONSTRAINTS: dict[str, list[str]] = {
    "sa-key-creation": [
        "iam.disableServiceAccountKeyCreation",
        "iam.managed.disableServiceAccountKeyCreation",
    ],
    "sa-key-upload": [
        "iam.disableServiceAccountKeyUpload",
        "iam.managed.disableServiceAccountKeyUpload",
    ],
    "domain-restricted-sharing": [
        "iam.allowedPolicyMemberDomains",
        "iam.managed.allowedPolicyMembers",
    ],
    "uniform-bucket-access": ["storage.uniformBucketLevelAccess"],
    "public-access-prevention": ["storage.publicAccessPrevention"],
    "os-login": ["compute.requireOsLogin", "compute.managed.requireOsLogin"],
    "vm-external-ip": ["compute.vmExternalIpAccess", "compute.managed.vmExternalIpAccess"],
    "serial-port": ["compute.disableSerialPortAccess"],
    "sql-public-ip": ["sql.restrictPublicIp"],
    "cmek-required": ["gcp.restrictNonCmekServices"],
}

# Why 200: one project rarely has more service accounts than this, and each one costs two calls.
DEFAULT_MAX_PER_KIND = 200


@dataclass
class CallResult:
    status: str  # ok, denied, not-enabled, not-found, error, unparseable
    data: Any = None
    text: str | None = None
    error: str | None = None


Runner = Callable[[list[str]], CallResult]


@dataclass
class Settings:
    projects: list[str] = field(default_factory=list)
    organizations: list[str] = field(default_factory=list)
    folders: list[str] = field(default_factory=list)
    assured_locations: list[str] = field(default_factory=lambda: ["us"])
    max_per_kind: int = DEFAULT_MAX_PER_KIND


def gcloud_runner(timeout: float = 120.0) -> Runner:
    """The default runner: validate, run gcloud, classify the result."""

    def run(argv: list[str]) -> CallResult:
        outcome = wrapper.run(argv, timeout=timeout)
        if outcome.returncode != 0:
            return CallResult(
                wrapper.classify_failure(outcome.stderr), error=outcome.stderr.strip()[:400]
            )
        data, text = wrapper.parse_output(outcome.stdout)
        if data is None:
            # Commands that print plain text or YAML (policy export, config get-value) are
            # kept as text. Any other command that returns non-JSON is a gap.
            return CallResult("ok" if wrapper.is_text_output(argv) else "unparseable", text=text)
        return CallResult("ok", data=data)

    return run


class Collector:
    def __init__(self, runner: Runner) -> None:
        self.runner = runner
        self.calls: list[dict[str, Any]] = []

    def call(self, kind: str, scope: str, target: str, argv: list[str], key: str = "") -> Any:
        """Run one call and record it. Returns the data when the call succeeded, else None."""
        try:
            wrapper.validate(argv)  # a battery call that is not read-only is a bug here
        except wrapper.ReadOnlyViolation as exc:
            raise RuntimeError(
                f"internal error: battery call {argv} is not read-only: {exc}"
            ) from exc
        result = self.runner(argv)
        self.calls.append(
            {
                "kind": kind,
                "scope": scope,
                "target": target,
                "key": key,
                "argv": argv,
                "status": result.status,
                "data": result.data,
                "text": result.text,
                "error": result.error,
            }
        )
        return result.data if result.status == "ok" else None


def _as_list(data: Any) -> list[dict[str, Any]]:
    return [d for d in data if isinstance(d, dict)] if isinstance(data, list) else []


def _short(name: str) -> str:
    return name.rsplit("/", 1)[-1]


def _collect_org_policies(c: Collector, scope: str, target: str, flag: str) -> None:
    for check, names in ORG_POLICY_CONSTRAINTS.items():
        for name in names:
            c.call(
                "org-policy",
                scope,
                target,
                ["org-policies", "describe", name, f"{flag}={target}", "--effective"],
                key=f"{check}|{name}",
            )


def collect_project(c: Collector, project: str, settings: Settings) -> None:
    s, t = "project", project
    p = f"--project={project}"
    c.call("project-describe", s, t, ["projects", "describe", project])
    c.call("ancestors", s, t, ["projects", "get-ancestors", project])
    c.call("iam-policy", s, t, ["projects", "get-iam-policy", project])
    accounts = _as_list(c.call("service-accounts", s, t, ["iam", "service-accounts", "list", p]))
    for account in accounts[: settings.max_per_kind]:
        email = account.get("email")
        if not email:
            continue
        c.call(
            "sa-keys",
            s,
            t,
            [
                "iam",
                "service-accounts",
                "keys",
                "list",
                f"--iam-account={email}",
                "--managed-by=user",
            ],
            key=email,
        )
        c.call(
            "sa-iam-policy",
            s,
            t,
            ["iam", "service-accounts", "get-iam-policy", email, p],
            key=email,
        )
    _collect_org_policies(c, s, t, "--project")
    c.call("services-enabled", s, t, ["services", "list", "--enabled", p])
    c.call("buckets", s, t, ["storage", "buckets", "list", "--raw", p])
    c.call("sql-instances", s, t, ["sql", "instances", "list", p])
    c.call("firewall-rules", s, t, ["compute", "firewall-rules", "list", p])
    c.call("networks", s, t, ["compute", "networks", "list", p])
    c.call("instances", s, t, ["compute", "instances", "list", p])
    c.call("project-info", s, t, ["compute", "project-info", "describe", p])
    c.call("clusters", s, t, ["container", "clusters", "list", p])

    services = _as_list(c.call("run-services", s, t, ["run", "services", "list", p]))
    for service in services[: settings.max_per_kind]:
        meta = service.get("metadata") or {}
        name = meta.get("name")
        region = (meta.get("labels") or {}).get("cloud.googleapis.com/location")
        if name and region:
            c.call(
                "run-iam-policy",
                s,
                t,
                ["run", "services", "get-iam-policy", name, f"--region={region}", p],
                key=f"{region}/{name}",
            )

    repos = _as_list(c.call("ar-repos", s, t, ["artifacts", "repositories", "list", p]))
    for repo in repos[: settings.max_per_kind]:
        full = repo.get("name", "")
        parts = full.split("/")
        # projects/P/locations/L/repositories/R
        if len(parts) == 6 and parts[2] == "locations":
            c.call(
                "ar-iam-policy",
                s,
                t,
                [
                    "artifacts",
                    "repositories",
                    "get-iam-policy",
                    parts[5],
                    f"--location={parts[3]}",
                    p,
                ],
                key=full,
            )

    c.call("binauthz-policy", s, t, ["container", "binauthz", "policy", "export", p])
    c.call("binauthz-attestors", s, t, ["container", "binauthz", "attestors", "list", p])

    pools = _as_list(
        c.call(
            "wif-pools",
            s,
            t,
            ["iam", "workload-identity-pools", "list", "--location=global", p],
        )
    )
    for pool in pools[: settings.max_per_kind]:
        pool_id = _short(pool.get("name", ""))
        if pool_id:
            c.call(
                "wif-providers",
                s,
                t,
                [
                    "iam",
                    "workload-identity-pools",
                    "providers",
                    "list",
                    f"--workload-identity-pool={pool_id}",
                    "--location=global",
                    p,
                ],
                key=pool_id,
            )


def collect_folder(c: Collector, folder: str) -> None:
    c.call(
        "iam-policy", "folder", folder, ["resource-manager", "folders", "get-iam-policy", folder]
    )
    _collect_org_policies(c, "folder", folder, "--folder")


def collect_organization(c: Collector, org: str, settings: Settings) -> None:
    s = "organization"
    c.call("iam-policy", s, org, ["organizations", "get-iam-policy", org])
    _collect_org_policies(c, s, org, "--organization")
    acm = _as_list(
        c.call(
            "vpcsc-policies",
            s,
            org,
            ["access-context-manager", "policies", "list", f"--organization={org}"],
        )
    )
    for policy in acm[: settings.max_per_kind]:
        policy_id = _short(policy.get("name", ""))
        if policy_id:
            c.call(
                "vpcsc-perimeters",
                s,
                org,
                ["access-context-manager", "perimeters", "list", f"--policy={policy_id}"],
                key=policy_id,
            )
    for location in settings.assured_locations:
        workloads = _as_list(
            c.call(
                "assured-workloads",
                s,
                org,
                ["assured", "workloads", "list", f"--organization={org}", f"--location={location}"],
                key=location,
            )
        )
        for workload in workloads[: settings.max_per_kind]:
            workload_id = _short(workload.get("name", ""))
            if workload_id:
                c.call(
                    "assured-violations",
                    s,
                    org,
                    [
                        "assured",
                        "workloads",
                        "violations",
                        "list",
                        f"--organization={org}",
                        f"--location={location}",
                        f"--workload={workload_id}",
                    ],
                    key=workload.get("name", workload_id),
                )


def collect(settings: Settings, runner: Runner) -> dict[str, Any]:
    """Run the whole battery and return the evidence document."""
    c = Collector(runner)
    c.call("identity", "global", "gcloud", ["config", "get-value", "account"])
    for org in settings.organizations:
        collect_organization(c, org, settings)
    for folder in settings.folders:
        collect_folder(c, folder)
    for project in settings.projects:
        collect_project(c, project, settings)
    return {
        "schema": SCHEMA,
        "collected_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "scopes": {
            "projects": settings.projects,
            "organizations": settings.organizations,
            "folders": settings.folders,
        },
        "calls": c.calls,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect read-only GCP evidence.")
    parser.add_argument("--project", action="append", default=[], help="project ID (repeatable)")
    parser.add_argument("--organization", action="append", default=[], help="organization ID")
    parser.add_argument("--folder", action="append", default=[], help="folder ID")
    parser.add_argument(
        "--assured-location",
        action="append",
        default=[],
        help="Assured Workloads location to list (repeatable; default: us)",
    )
    parser.add_argument("--timeout", type=float, default=120.0, help="seconds per gcloud call")
    parser.add_argument("--out", required=True, help="path of the evidence JSON file to write")
    return parser


def main(argv: list[str] | None = None, runner: Runner | None = None) -> int:
    args = _parser().parse_args(argv)
    if not (args.project or args.organization or args.folder):
        print(
            "gcp_collect: give at least one --project, --organization or --folder. "
            "Ask the user which scope to review; do not guess.",
            file=sys.stderr,
        )
        return 2
    settings = Settings(
        projects=args.project,
        organizations=args.organization,
        folders=args.folder,
        assured_locations=args.assured_location or ["us"],
    )
    try:
        evidence = collect(settings, runner or gcloud_runner(args.timeout))
    except wrapper.GcloudNotFound as exc:
        print(f"gcp_collect: {exc}", file=sys.stderr)
        return 3
    out = Path(args.out)
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except OSError as exc:
        print(
            f"gcp_collect: cannot write {out}: {exc}. Choose a writable --out path.",
            file=sys.stderr,
        )
        return 2
    counts: dict[str, int] = {}
    for call in evidence["calls"]:
        counts[call["status"]] = counts.get(call["status"], 0) + 1
    summary = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
    print(f"gcp_collect: wrote {out} ({summary})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
