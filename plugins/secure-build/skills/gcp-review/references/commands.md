# Command catalog

Sources (fetched 2026-10-16): the gcloud reference pages under
https://docs.cloud.google.com/sdk/gcloud/reference/ for each command named below, the
Artifact Registry, GKE and Workload Identity REST references, and
https://docs.cloud.google.com/asset-inventory/docs/overview.
Output field names marked UNVERIFIED were not confirmed against a live project, because
gcloud was not available when this file was written. The analyzer accepts both common spellings
where known, and records a gap when a field is missing.

## Contents

- [How to call gcloud](#how-to-call-gcloud)
- [What the wrapper accepts](#what-the-wrapper-accepts)
- [The evidence battery](#the-evidence-battery)
- [Follow-up patterns](#follow-up-patterns)
- [Read roles](#read-roles)
- [Failure statuses](#failure-statuses)
- [Continuous alternatives](#continuous-alternatives)

## How to call gcloud

Every call is `python3 ${CLAUDE_SKILL_DIR}/scripts/gcloud_readonly.py <arguments>` with the
arguments written as separate words and no leading `gcloud`. The wrapper validates them,
appends `--format=json` (except for the two commands that print text) and `--quiet`, runs
gcloud with no standard input and with prompts and API-enable offers switched off, and prints
the output.

Exit codes: 0 success, 1 gcloud failed (stderr ends with `classified=<status>`), 2 rejected
before anything ran, 3 gcloud not installed.

## What the wrapper accepts

- **Command paths**: a fixed set of read-only paths in `ALLOWED_COMMANDS` inside
  `gcloud_readonly.py`. They cover `list`, `describe`, `get-iam-policy`, `get-ancestors`,
  `search-all-resources`, `search-all-iam-policies`, `analyze-iam-policy`,
  `container binauthz policy export`, `config get-value` and `version`. A path that is not in
  the set is refused, including release-track commands (`alpha`, `beta`).
- **Flags**: only the flags in `VALUE_FLAGS` and `BOOLEAN_FLAGS` (project, organization,
  folder, location, region, zone, filter, limit, page size, sort order, query, scope, policy,
  workload, workload identity pool, IAM account, managed-by, created-before, asset types,
  `--effective`, `--enabled`, `--available`, `--raw`).
- **Refused flags**: `--impersonate-service-account`, `--account`, `--access-token-file`,
  `--credential-file-override`, `--configuration`, `--format`, `--flatten`, `--quiet`,
  `--verbosity`, `--log-http`, `--billing-project`. Each has a message that says what to do
  instead.
- **Characters**: shell syntax and quote characters in any argument are refused. Values use a
  small safe character set; only `--filter` and `--query` values may hold spaces and `*`.
- **Mutating words** such as `set-iam-policy`, `add-iam-policy-binding`, `delete`, `create`,
  `update`, `enable`, `disable`, `deploy`, `import`, `ssh` and `get-credentials` are refused
  with a message that names the word.

The wrapper is a guard against mistakes. It does not stop anyone from running gcloud
directly. For a guarantee, use a PreToolUse hook in the `guardrails` plugin.

## The evidence battery

`gcp_collect.py` runs these calls. `P` is a project, `O` an organization, `F` a folder. Each
call is recorded with its own status.

| Kind | Scope | Command (after `gcloud`) | Feeds |
| --- | --- | --- | --- |
| identity | global | `config get-value account` | report header |
| project-describe | P | `projects describe P` | context |
| ancestors | P | `projects get-ancestors P` | GCP-AW-003 |
| iam-policy | P, O, F | `projects get-iam-policy P`, `organizations get-iam-policy O`, `resource-manager folders get-iam-policy F` | IAM and LOG rules |
| service-accounts | P | `iam service-accounts list --project P` | drives the next two |
| sa-keys | P | `iam service-accounts keys list --iam-account SA --managed-by=user` | GCP-IAM-004, GCP-IAM-005 |
| sa-iam-policy | P | `iam service-accounts get-iam-policy SA --project P` | GCP-IAM-008 |
| org-policy | P, O, F | `org-policies describe CONSTRAINT --project P --effective` (or `--organization`, `--folder`), once per constraint name | GCP-ORG rules |
| services-enabled | P | `services list --enabled --project P` | GCP-LOG-002, GCP-AR-002 |
| buckets | P | `storage buckets list --raw --project P` | GCP-STO rules |
| sql-instances | P | `sql instances list --project P` | GCP-SQL rules |
| firewall-rules | P | `compute firewall-rules list --project P` | GCP-NET-002, GCP-NET-003 |
| networks | P | `compute networks list --project P` | GCP-NET-001 |
| instances | P | `compute instances list --project P` | GCP-GCE rules |
| project-info | P | `compute project-info describe --project P` | GCP-GCE-004 |
| clusters | P | `container clusters list --project P` | GCP-GKE rules |
| run-services | P | `run services list --project P` | GCP-RUN rules, drives the next |
| run-iam-policy | P | `run services get-iam-policy SERVICE --region R --project P` | GCP-RUN-001 |
| ar-repos | P | `artifacts repositories list --project P` | GCP-AR rules, drives the next |
| ar-iam-policy | P | `artifacts repositories get-iam-policy REPO --location L --project P` | GCP-AR-001 |
| binauthz-policy | P | `container binauthz policy export --project P` (YAML text) | GCP-BINAUTHZ rules |
| binauthz-attestors | P | `container binauthz attestors list --project P` | evidence |
| wif-pools | P | `iam workload-identity-pools list --location=global --project P` | drives the next |
| wif-providers | P | `iam workload-identity-pools providers list --workload-identity-pool POOL --location=global --project P` | GCP-WIF rules |
| vpcsc-policies | O | `access-context-manager policies list --organization O` | GCP-VPCSC rules |
| vpcsc-perimeters | O | `access-context-manager perimeters list --policy POLICY` | GCP-VPCSC rules |
| assured-workloads | O | `assured workloads list --organization O --location L` | GCP-AW rules |
| assured-violations | O | `assured workloads violations list --organization O --location L --workload W` | GCP-AW-002 |

Per-resource calls (service accounts, Cloud Run services, repositories, pools) are capped per
kind in `gcp_collect.py` (`DEFAULT_MAX_PER_KIND`). A project with more resources than the cap is
partly covered; say so in the report.

## Follow-up patterns

Run these through the wrapper when a finding needs a closer look. Replace the capitalized words.

- Who holds a role on one project: `projects get-iam-policy P`, then filter the JSON.
- Where a member appears across the organization:
  `asset search-all-iam-policies --scope=organizations/O --query=policy:MEMBER`.
- What a member can do through impersonation:
  `asset analyze-iam-policy --full-resource-name=FULL_NAME --identity=MEMBER` (check the
  current flag set in the reference first).
- One organization policy, effective at a project:
  `org-policies describe CONSTRAINT --project P --effective`.
- Policies set directly on a resource: `org-policies list --project P`.
- A cluster in full: `container clusters describe NAME --location L --project P`.
- A Cloud Run service in full: `run services describe NAME --region R --project P`.
- Assured Workloads detail:
  `assured workloads describe organizations/O/locations/L/workloads/W`.
- Security Command Center findings: `scc findings list` takes arguments that change between
  versions; fetch the current reference page before the first call.

## Read roles

Typical read-only roles for the reviewing identity. Confirm names and scopes in the current
IAM roles reference before asking anyone to grant them.

| Role | Gives |
| --- | --- |
| `roles/iam.securityReviewer` | Read IAM policies and many security settings |
| `roles/browser` | Read the resource hierarchy |
| `roles/orgpolicy.policyViewer` | Read organization policies |
| `roles/serviceusage.serviceUsageViewer` | List enabled services |
| `roles/cloudasset.viewer` | Cloud Asset Inventory reads |
| `roles/accesscontextmanager.policyReader` | VPC Service Controls policies and perimeters |
| `roles/assuredworkloads.reader` | Assured Workloads reads |

Service-specific reads (Cloud Run, GKE, Cloud SQL, Compute, Storage, Artifact Registry) need a
viewer role for each service. A denied call becomes a gap, so a partial grant still produces a
useful report.

## Failure statuses

| Status | Meaning | What to tell the user |
| --- | --- | --- |
| ok | Data returned | nothing |
| denied | Permission denied (403) | which role would close the gap |
| not-enabled | API not enabled in the project | the API name; enabling it is the user's call |
| not-found | Resource or constraint does not exist | usually expected for the second spelling of an org policy constraint |
| error | Anything else | the first line of the error |
| unparseable | Output was not JSON | re-run the call by hand |

## Continuous alternatives

- Security Command Center: https://docs.cloud.google.com/security-command-center/docs/security-command-center-overview
  describes the offering and its service tiers. Fetch the tier names and any change notices
  before recommending one.
- Cloud Asset Inventory: https://docs.cloud.google.com/asset-inventory/docs/overview covers
  search, export, history, IAM analysis and feeds.
- Terraform: the `terraform` plugin in `claude-plugins-official` (a HashiCorp Terraform MCP
  server, run from a container image) looks up provider documentation. It needs Docker and may
  need a Terraform Cloud or Enterprise token for private registry features.
