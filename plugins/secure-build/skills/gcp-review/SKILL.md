---
name: gcp-review
description: >-
  Runs a read-only security review of Google Cloud projects with gcloud and reports evidence,
  gaps and drafted fixes without changing anything. Use when someone asks to review, audit or
  harden a GCP project, check IAM least privilege, basic roles (owner, editor), service account
  keys, allUsers or allAuthenticatedUsers bindings, organization policies, Workload Identity
  Federation for GitHub Actions or GitLab CI, VPC Service Controls, CMEK, audit logs and Data
  Access logs, Artifact Registry, Binary Authorization, Cloud Run or GKE hardening, or Assured
  Workloads for FedRAMP Moderate, FedRAMP High, IL4 or IL5, even if they do not name this skill
  or mention gcloud. Also use when someone asks to "just fix" a risky GCP setting, because this
  skill drafts the fix for a person to run. Writing new infrastructure code and reviewing a
  Dockerfile belong to other skills. For the pipeline side of keyless auth (a workflow or
  .gitlab-ci.yml change), use ci-harden.
allowed-tools:
  - Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/*)
  - Read
---

# GCP security review (read-only)

This skill reviews Google Cloud configuration with `gcloud`, writes down what it found and
what it could not check, and drafts fixes. It never changes a project.

## Rules for the whole review

1. **Read-only.** Run every gcloud call through the wrapper:
   `python3 ${CLAUDE_SKILL_DIR}/scripts/gcloud_readonly.py <gcloud arguments without "gcloud">`.
   The wrapper accepts only read commands from an allowlist and exits 2 on anything else.
   When it refuses a command, report the refusal. Do not rephrase the command to get past it and
   do not run `gcloud` directly.
2. **Fixes are drafts.** Put each fix in the report as a command or Terraform snippet. Never
   run one, even when the user says "just fix it": show the draft, say a person runs it through
   the team's change process, and stop.
3. **Evidence and gaps only.** Never write that a project is compliant, FedRAMP ready or
   authorized, and never imply it. A person with the authority decides. A control the review
   could not read is a gap and stays in the report as one.
4. **Fetch fast-moving facts at run time** (step 1). Do not answer from memory about benchmark
   editions, Assured Workloads regimes or organization policy constraint names.
5. **State the limits honestly.** The `allowed-tools` field above pre-approves these scripts so
   they run without a prompt. It does not restrict Claude to them. The wrapper guards against
   mistakes, and Claude can still skip it. A rule that must hold every time belongs in a
   PreToolUse hook in the `guardrails` plugin; recommend that hook when the user needs a hard
   guarantee, and say whether it is installed.

## Before starting

- Check the CLI: `python3 ${CLAUDE_SKILL_DIR}/scripts/gcloud_readonly.py version`. Exit 3 means
  gcloud is missing; tell the user to install the Google Cloud CLI and sign in, then stop.
- Check who is signed in: `python3 ${CLAUDE_SKILL_DIR}/scripts/gcloud_readonly.py config get-value account`.
  Show the account to the user and ask whether it is the identity meant for review. The wrapper
  never switches identity. A read-only reviewer account or impersonated service account is set
  up by the user in their own gcloud configuration. Typical read roles are listed in
  [references/commands.md](references/commands.md).
- Ask for the scope: project IDs, and an organization ID or folder ID if inherited settings
  matter. Do not guess project IDs. Ask whether any workload is under Assured Workloads, and
  which CIS benchmark edition the team holds, if any.

## Step 1: fetch current facts

Use WebFetch on these sources and note the date. If a fetch fails, record a gap and say which
source failed.

| Fact | Source |
| --- | --- |
| Current CIS Google Cloud Platform Foundation Benchmark edition | https://www.cisecurity.org/benchmark/google_cloud_computing_platform |
| Organization policy constraint names (legacy and managed forms) | https://docs.cloud.google.com/resource-manager/docs/organization-policy/org-policy-constraints |
| Assured Workloads regimes and `gcloud assured` commands | https://docs.cloud.google.com/assured-workloads/docs/overview and https://docs.cloud.google.com/sdk/gcloud/reference/assured |
| Workload Identity Federation guidance for GitHub and GitLab | https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines |

Compare each fetched fact with what [references/checks.md](references/checks.md) and
[references/assured-workloads.md](references/assured-workloads.md) record. When they differ,
trust the fetched page, tell the user what changed, and pass the fetched benchmark edition to
the analyzer in step 3 so it drops benchmark IDs it cannot vouch for.

## Step 2: collect evidence

Run the collector. It runs a fixed battery of read-only calls and writes one JSON file:

```sh
python3 ${CLAUDE_SKILL_DIR}/scripts/gcp_collect.py --project PROJECT_ID [--project ...] \
  [--organization ORG_ID] [--folder FOLDER_ID] [--assured-location us] \
  --out gcp-review/EVIDENCE_DATE/evidence.json
```

- A call that is denied, needs an API that is not enabled, or fails is recorded with a status
  and the run continues. Those calls become gaps in the report.
- Without `--organization`, inherited settings (organization policies, organization IAM, VPC
  Service Controls, Assured Workloads) are not collected, and the report says so.
- The evidence file holds account emails and resource names. Keep it with the team's audit
  evidence and out of version control.
- Exit 3 means gcloud is missing. Exit 2 means a bad argument; the message names the fix.

## Step 3: analyze

```sh
python3 ${CLAUDE_SKILL_DIR}/scripts/gcp_analyze.py gcp-review/EVIDENCE_DATE/evidence.json \
  --out-dir gcp-review/EVIDENCE_DATE --benchmark-edition FETCHED_EDITION
```

This writes `findings.json` and `report.md`. It is offline and deterministic. Useful options:
`--key-max-age-days N` (default 90; use the team's rotation limit), `--fail-on SEVERITY`
(exit 1 for CI-style gating), `--format json|markdown|both`.

## Step 4: write the report

Read `report.md` and deliver it with a short summary on top. Keep these three sections:

1. **Findings**: severity, rule ID, resource, the evidence snippet and any benchmark ID the
   analyzer attached. Order by severity. Do not drop a finding because it looks intentional;
   mark it "needs a decision" instead and say who decides.
2. **Not checked (gaps)**: every denied, not-enabled or failed call, every area the skill does
   not cover, and every fetch that failed. For each gap that a permission or API would close,
   name it (see [references/commands.md](references/commands.md) for the read roles).
3. **Drafted fixes (not executed)**: the commands and Terraform from the analyzer, each with
   its note. Add the order of operations a change needs (grant the narrower role first, test
   in a non-production project, apply org policies to a folder before the organization).

Cite a standard only through what the analyzer attached. Benchmark IDs are tied to one edition;
if the fetched edition differs from the analyzer's map, cite none and say so. Do not add control
IDs from memory.

For ad hoc follow-up questions, use the wrapper with the patterns in
[references/commands.md](references/commands.md). Read `findings.json` for detail.

## GitHub and GitLab pipelines

Workload Identity Federation providers are checked the same way for both hosts. GitHub Actions
uses issuer `https://token.actions.githubusercontent.com`, GitLab SaaS uses
`https://gitlab.com`, and a self-managed GitLab uses its own URL. A provider with no attribute
condition, or a condition that names no owner or group claim, is a finding. The fix draft shows
an example condition for each host; [references/checks.md](references/checks.md) has the claims.

## Infrastructure as code and continuous alternatives

- When the team keeps infrastructure in Terraform, make the fix a Terraform change. The
  official `terraform` plugin in `claude-plugins-official` runs the HashiCorp Terraform MCP
  server, which looks up provider and module documentation. Use it to check resource arguments
  before drafting; the analyzer's snippets use the `google_org_policy_policy` resource for
  organization policies.
- This review is a point-in-time check. For continuous coverage, name **Security Command
  Center** (findings and compliance monitoring) and **Cloud Asset Inventory** (search and
  analysis of resources and IAM policies, with `gcloud asset search-all-iam-policies` allowed
  through the wrapper). Fetch the current editions and pricing pages before recommending one;
  see [references/commands.md](references/commands.md) for the links.

## Regulated workloads

For FedRAMP Moderate or High and IL4 or IL5 questions, read
[references/assured-workloads.md](references/assured-workloads.md), run the
`--organization` collection, and report what Assured Workloads shows (regimes, folders,
violations) as configuration evidence. A person with the authority decides what it means.

## Files

| File | Use |
| --- | --- |
| `scripts/gcloud_readonly.py` | Run. The only way to call gcloud. |
| `scripts/gcp_collect.py` | Run. Writes the evidence file. |
| `scripts/gcp_analyze.py` | Run. Writes `findings.json` and `report.md`. |
| `scripts/gcp_rules.py` | Read only to explain why a finding fired. |
| [references/commands.md](references/commands.md) | The call battery, wrapper allowlist, follow-up patterns, read roles. |
| [references/checks.md](references/checks.md) | Every rule, its inputs, standards handling, org policy names. |
| [references/assured-workloads.md](references/assured-workloads.md) | Assured Workloads commands and what to fetch. |
| `references/cis-gcp-map.json` | Benchmark IDs per rule for one edition. Data for the analyzer. |
