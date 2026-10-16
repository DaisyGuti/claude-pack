# Checks, rules and standards handling

Sources (fetched 2026-10-16):

- Organization policy constraints: https://docs.cloud.google.com/resource-manager/docs/organization-policy/org-policy-constraints,
  https://docs.cloud.google.com/resource-manager/docs/organization-policy/restricting-service-accounts,
  https://docs.cloud.google.com/resource-manager/docs/organization-policy/restricting-domains,
  https://docs.cloud.google.com/storage/docs/org-policy-constraints,
  https://docs.cloud.google.com/compute/docs/access/organization-policies,
  https://docs.cloud.google.com/kms/docs/cmek-org-policy
- Workload Identity Federation: https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines
- Cloud Run: https://docs.cloud.google.com/run/docs/securing/ingress,
  https://docs.cloud.google.com/run/docs/securing/managing-access,
  https://docs.cloud.google.com/run/docs/authenticating/public
- Artifact Registry: https://docs.cloud.google.com/artifact-registry/docs/reference/rest/v1/projects.locations.repositories,
  https://docs.cloud.google.com/artifact-analysis/docs/os-overview
- GKE: https://docs.cloud.google.com/kubernetes-engine/docs/reference/rest/v1/projects.locations.clusters
- CIS Google Cloud Platform Foundation Benchmark: https://www.cisecurity.org/benchmark/google_cloud_computing_platform

The analyzer reads the evidence file and applies the rules below. `scripts/gcp_rules.py` is the
source of truth for the logic; this file explains it.

## Contents

- [Rules](#rules)
- [Organization policy constraints](#organization-policy-constraints)
- [How an organization policy is judged](#how-an-organization-policy-is-judged)
- [Workload Identity Federation claims](#workload-identity-federation-claims)
- [Standards handling](#standards-handling)
- [Deliberate skips](#deliberate-skips)
- [Unverified assumptions](#unverified-assumptions)

## Rules

Severity is the default; a rule can lower it for a specific case (a disabled key, a service
account instead of a person). Each rule is deterministic and every finding carries the evidence
snippet that triggered it.

| Rule | Flags | Default severity |
| --- | --- | --- |
| GCP-IAM-001 | `roles/owner`, `roles/editor` or `roles/viewer` granted to a user, group or domain at project, folder or organization scope | high (viewer: low) |
| GCP-IAM-002 | `roles/owner` or `roles/editor` granted to a service account | high |
| GCP-IAM-003 | any role granted to `allUsers` or `allAuthenticatedUsers` in a project, folder or organization policy | critical |
| GCP-IAM-004 | a user-managed service account key exists (recent enough to pass the age check) | medium (disabled: low) |
| GCP-IAM-005 | a user-managed key older than `--key-max-age-days` | high |
| GCP-IAM-006 | the default compute service account holds `roles/editor` | high |
| GCP-IAM-007 | `roles/iam.serviceAccountUser` or `roles/iam.serviceAccountTokenCreator` granted at project, folder or organization scope | medium (to a service account: low) |
| GCP-IAM-008 | impersonation roles on a single service account granted to the public (critical) or to a user, group or domain (low, for review) | low |
| GCP-ORG-001 to GCP-ORG-010 | an organization policy constraint is not enforced; see the next section | varies |
| GCP-LOG-001 | no `allServices` audit config logging `DATA_READ` and `DATA_WRITE` in the project or organization policy, and no organization or folder policy in the evidence provides one | medium |
| GCP-LOG-002 | `cloudasset.googleapis.com` is not enabled | low |
| GCP-NET-001 | a network named `default` exists | medium |
| GCP-NET-002, GCP-NET-003 | an enabled ingress firewall rule from `0.0.0.0/0` or `::/0` covers TCP 22 (SSH) or TCP 3389 (RDP), including port ranges and the `all` protocol | high |
| GCP-VPCSC-001 | organization scope only: no access policy, or an access policy with no perimeters | medium |
| GCP-VPCSC-002 | a perimeter with no resources in its enforced configuration | low |
| GCP-GCE-001, GCP-GCE-002 | an instance runs as the default compute service account; 002 adds the `cloud-platform` scope | medium, high |
| GCP-GCE-003 | an instance has an external IP | medium |
| GCP-GCE-004 | `enable-oslogin` is not `TRUE` in project metadata and no OS Login org policy is enforced | medium |
| GCP-STO-001 | a bucket without uniform bucket-level access | medium |
| GCP-STO-002 | buckets without public access prevention enforced (one aggregated finding per project) | low |
| GCP-STO-003 | buckets with no customer-managed key (aggregated) | info |
| GCP-SQL-001 | a Cloud SQL instance has a public IP | high |
| GCP-SQL-002 | no customer-managed key (aggregated) | info |
| GCP-SQL-003 | an authorized network of `0.0.0.0/0` | critical |
| GCP-RUN-001 | `allUsers` or `allAuthenticatedUsers` holds `roles/run.invoker` | high |
| GCP-RUN-002 | annotation `run.googleapis.com/invoker-iam-disabled` is `true` (the service is public without an IAM binding) | high |
| GCP-RUN-003 | ingress annotation is `all` or unset | low |
| GCP-RUN-004 | the service account is unset or the default compute account | medium |
| GCP-GKE-001 | private nodes are off | high |
| GCP-GKE-002 | public control plane endpoint with no authorized networks | high |
| GCP-GKE-003 | no Workload Identity pool (standard clusters) | medium |
| GCP-GKE-004 | Shielded nodes off (standard clusters) | medium |
| GCP-GKE-005 | no network policy and no `ADVANCED_DATAPATH` (standard clusters) | medium |
| GCP-GKE-006 | no release channel | low |
| GCP-GKE-007 | Binary Authorization not enforced on the cluster | medium |
| GCP-GKE-008 | legacy ABAC on | high |
| GCP-WIF-001 | a provider has no attribute condition, or the condition is `true` | high |
| GCP-WIF-002 | a GitHub Actions or GitLab SaaS provider whose condition names no owner or group claim | high |
| GCP-AR-001 | a repository IAM policy grants a role to the public | critical |
| GCP-AR-002 | Docker repositories exist and `containerscanning.googleapis.com` is not enabled | medium |
| GCP-AR-003 | a Docker repository has scanning disabled; a missing setting is a gap | medium |
| GCP-AR-004 | Docker repositories that allow tags to be overwritten (aggregated) | low |
| GCP-AR-005, GCP-AR-006 | no cleanup policies, no customer-managed key (aggregated) | info |
| GCP-BINAUTHZ-001 | the project policy's default rule is `ALWAYS_ALLOW` | medium |
| GCP-BINAUTHZ-002 | the default rule only logs (`DRYRUN_AUDIT_LOG_ONLY`) | low |
| GCP-AW-001 | an Assured Workloads workload exists; records name, display name and regime | info |
| GCP-AW-002 | a workload has `UNRESOLVED` violations | medium |
| GCP-AW-003 | a project's ancestor folders match no listed workload | info |

GCP-AW-001 and GCP-AW-003 describe configuration. They say nothing about whether a regime is met.

## Organization policy constraints

The collector asks for the effective policy under every spelling below. Google publishes both a
legacy name and a managed name for several constraints; either one enforced satisfies the
check. Fetch the constraint reference at run time and update this table in the report if a
name moved.

| Check | Rule | Names queried |
| --- | --- | --- |
| sa-key-creation | GCP-ORG-001 | `iam.disableServiceAccountKeyCreation`, `iam.managed.disableServiceAccountKeyCreation` |
| sa-key-upload | GCP-ORG-002 | `iam.disableServiceAccountKeyUpload`, `iam.managed.disableServiceAccountKeyUpload` |
| domain-restricted-sharing | GCP-ORG-003 | `iam.allowedPolicyMemberDomains`, `iam.managed.allowedPolicyMembers` |
| uniform-bucket-access | GCP-ORG-004 | `storage.uniformBucketLevelAccess` |
| public-access-prevention | GCP-ORG-005 | `storage.publicAccessPrevention` |
| os-login | GCP-ORG-006 | `compute.requireOsLogin`, `compute.managed.requireOsLogin` |
| vm-external-ip | GCP-ORG-007 | `compute.vmExternalIpAccess`, `compute.managed.vmExternalIpAccess` |
| serial-port | GCP-ORG-008 | `compute.disableSerialPortAccess` |
| sql-public-ip | GCP-ORG-009 | `sql.restrictPublicIp` |
| cmek-required | GCP-ORG-010 | `gcp.restrictNonCmekServices` |

The constraint reference listed the managed names for key creation, key upload, domain
sharing, OS Login and VM external IP access when it was read. The Compute organization policy
page listed only the legacy `compute.requireOsLogin` and `compute.vmExternalIpAccess`, so those
two managed spellings are the least certain. A constraint that does not exist returns
`not-found`, which the analyzer treats as unknown. Unknown produces a gap, and a finding only when another spelling was read and is not enforced.

Related constraints worth naming to the user when a Cloud Run finding appears:
`run.managed.requireInvokerIam` (blocks disabling the invoker IAM check) and the domain
restricted sharing constraint (blocks granting roles to `allUsers`).

## How an organization policy is judged

For each scope the analyzer groups the calls for one check and decides:

- **enforced** when any unconditional rule has `enforce: true`, `denyAll: true`, or a
  non-empty `allowedValues` or `deniedValues`.
- **not enforced** when no rule does, or the effective policy has no rules. A finding is raised
  only when at least one spelling was read successfully and none is enforced.
- **unknown** when every call failed or only conditional rules exist. The check becomes a gap
  with the statuses, so a denied read produces a gap about the read itself.

## Workload Identity Federation claims

Google's deployment-pipeline guidance says an attribute condition that restricts tokens to your
organization or group is required for GitHub, GitLab SaaS and similar hosts that share one
issuer across all customers.

| Host | Issuer URI | Claims the analyzer accepts as scoping the token |
| --- | --- | --- |
| GitHub Actions | `https://token.actions.githubusercontent.com` | `repository_owner`, `repository_owner_id`, `repository`, `repository_id` |
| GitLab SaaS | `https://gitlab.com` | `namespace_id`, `namespace_path`, `project_id`, `project_path` |
| GitLab self-managed | the instance's own URL | not recognized; only the missing-condition rule applies |

Example conditions the fix draft shows: `assertion.repository_owner=='YOUR_ORG'` and
`assertion.namespace_id=='YOUR_GROUP_ID'`. A condition on `assertion.sub` alone is flagged
because it does not name the owner claim the guidance asks for; a person can judge whether a
specific `sub` pattern is enough. The analyzer reads the condition text only. Whether the
service account bindings behind the provider are narrow enough needs a human look at the pool's
principal sets.

## Standards handling

The analyzer attaches benchmark IDs from `references/cis-gcp-map.json` and only when the
edition in use matches the map's edition.

- **Edition**: the CIS page listed the Google Cloud Platform Foundation Benchmark at 5.0.0 on
  2026-10-16. The edition number changes the section numbering (5.0.0 added a new section for
  organization resource settings), so the skill fetches the edition at run time and passes it to
  `--benchmark-edition`. A different edition drops all IDs and prints a notice.
- **How the IDs were verified**: the CIS document is behind a CIS account and was not read.
  The IDs and titles in the map come from the open-source Prowler compliance file
  `prowler/compliance/gcp/cis_5.0_gcp.json`, which lists the 5.0.0 recommendations. That is a
  third-party listing, so every report says to confirm each ID against the edition the team holds.
- **What is mapped**: only rules whose recommendation title plainly matches the rule (service
  account keys, service account administrative roles, Service Account User at project level,
  audit logging, Cloud Asset Inventory, default network, SSH and RDP from the internet, VPC
  Service Controls, default service account and public IP on instances, OS Login, uniform
  bucket-level access, Cloud SQL public IP and open networks).
- **What is left out and why**: basic roles on people, public IAM members, organization
  policies, Cloud Run, GKE, Workload Identity Federation, Artifact Registry and Binary
  Authorization have no recommendation in the Foundation benchmark whose title matches the
  check. GKE has its own CIS benchmark; the skill does not cite it because its edition and
  numbering were not read. Findings for those rules carry no benchmark ID.
- NIST SP 800-53 and FedRAMP control IDs are not attached. Mapping GCP settings to them is a
  judgment for the team's assessor.

## Deliberate skips

- The Google APIs Service Agent (`<number>@cloudservices.gserviceaccount.com`) holds Editor by
  design in many projects and is not reported under GCP-IAM-002.
- `roles/viewer` on a service account is not reported.
- `deleted:` principals in a policy are not reported.
- Instances created by GKE (the `goog-gke-node` label or a `gke-` name prefix) are skipped for
  the instance rules, because the cluster rules cover them.
- Autopilot clusters skip GCP-GKE-003 to GCP-GKE-005. Verify Autopilot's current security
  defaults in the GKE documentation before relying on that skip.
- A disabled key is reported as low severity whatever its age.

## Unverified assumptions

These come from API references and documentation. No live project has confirmed them:

- `gcloud iam service-accounts keys list --format=json` includes `keyType`, `validAfterTime`
  and `disabled` for each key.
- `gcloud org-policies describe --effective --format=json` returns `spec.rules[]` with
  `enforce`, `denyAll`, `allowAll` and `values`.
- `gcloud run services list --format=json` returns Knative-style objects with
  `metadata.annotations` and `spec.template.spec.serviceAccountName`.
- `gcloud container binauthz policy export` prints YAML; the analyzer also accepts JSON.
- `gcloud storage buckets list --raw` returns API-shaped (camelCase) bucket objects. The
  analyzer also accepts the snake_case spellings.
- `networkConfig.defaultEnablePrivateNodes` is read as a second way to find private nodes.
- The Assured Workloads `resources[].resourceId` for a folder matches the folder ID that
  `projects get-ancestors` returns.
- Setting `CLOUDSDK_CORE_SHOULD_PROMPT_TO_ENABLE_API=false` suppresses the API-enable offer.
  The wrapper also closes standard input and passes `--quiet`, so the prompt cannot be answered
  either way.

When a live run shows a different shape, fix `gcp_rules.py` and add a test with the real shape.
