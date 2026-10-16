# Assured Workloads

Sources (fetched 2026-10-16):

- Overview and the list of compliance regimes and control packages:
  https://docs.cloud.google.com/assured-workloads/docs/overview
- gcloud reference: https://docs.cloud.google.com/sdk/gcloud/reference/assured (groups
  `operations` and `workloads`; subgroup `workloads violations`),
  `.../assured/workloads/list`, `.../assured/workloads/describe`,
  `.../assured/workloads/violations/list`
- Workload and Violation resources:
  https://docs.cloud.google.com/assured-workloads/docs/reference/rest/v1/organizations.locations.workloads
  and `.../workloads.violations`

Assured Workloads is a Google Cloud service that applies a set of controls (data location,
personnel access, encryption, allowed services) to a folder, using organization policies and
monitoring. It supports a compliance program; authorization decisions stay with the people who hold that authority.

## Contents

- [What to fetch at run time](#what-to-fetch-at-run-time)
- [Regimes seen on the fetch date](#regimes-seen-on-the-fetch-date)
- [What gcloud assured offers](#what-gcloud-assured-offers)
- [What the review records](#what-the-review-records)
- [What the review cannot tell you](#what-the-review-cannot-tell-you)
- [Questions to put to the user](#questions-to-put-to-the-user)

## What to fetch at run time

Regimes, supported locations and supported products change. Before reporting, fetch:

1. The overview page above, for the current regime names.
2. The `gcloud assured` reference page, for the current command groups and flags.
3. The supported locations page that the `workloads list` reference links to, so the
   `--assured-location` values passed to the collector are real locations.

Quote the names from the fetched page in the report. If the fetch fails, say so and name the
regime only as the user stated it.

## Regimes seen on the fetch date

For orientation only. The overview page listed these regulatory control packages among others:
FedRAMP Moderate, FedRAMP High, Impact Level 2 (IL2), Impact Level 4 (IL4), Impact Level 5
(IL5), CJIS, ITAR, IRS Publication 1075, Canada Protected B, Canada Controlled Goods Program,
and Healthcare and Life Sciences Controls. It also listed a long set of regional data
boundary packages. The run-time fetch decides what exists today.

In the REST API the regime appears as the `complianceRegime` field of a workload. Its enum
values were not on the page that was read, so report the string the API returns and do not
translate it.

## What gcloud assured offers

| Command | Does | Allowed by the wrapper |
| --- | --- | --- |
| `assured workloads list --organization O --location L` | Lists workloads in a location (both flags required) | yes |
| `assured workloads describe NAME` | One workload; NAME is `organizations/O/locations/L/workloads/W` | yes |
| `assured workloads violations list --organization O --location L --workload W` | Violations of one workload (all three flags required) | yes |
| `assured workloads violations describe` | One violation | yes |
| `assured operations list`, `assured operations describe` | Long-running operations | not in the allowlist; add with a test if a review needs them |
| `assured workloads create`, `update`, `delete`, `enable-resource-monitoring` | Changes workloads | refused |
| `assured workloads violations acknowledge` | Marks a violation as an exception | refused |

A workload exists in one location, so the collector lists each `--assured-location` you pass
(default `us`). A workload in another location is not seen unless you pass that location.

## What the review records

With `--organization`, the collector lists workloads and their violations and reads each
project's ancestors. The analyzer then reports:

- GCP-AW-001: each workload's name, display name and `complianceRegime`.
- GCP-AW-002: workloads with violations whose state is `UNRESOLVED`, with their categories.
  Violation states in the REST reference are `RESOLVED`, `UNRESOLVED` and `EXCEPTION`.
- GCP-AW-003: projects whose ancestor folders match no workload resource in the listed
  locations. It compares `projects get-ancestors` ids with each workload's
  `resources[].resourceId`. The resource reference describes that id as a project number for
  projects; for a folder it is assumed to be the folder id.

## What the review cannot tell you

- Whether the workload's regime is the right one for the data. That is a decision about the
  data's categorization, made by the system owner and the authorizing official.
- Whether the controls are sufficient for FedRAMP or DoD impact-level authorization. The
  authorization package, the agency's assessment and the authorizing official decide that.
- Whether every resource in the folder complies. Violations show what Google's monitoring
  detected, which is narrower than a full assessment.
- Anything outside the listed locations, organizations and folders.

Report these limits next to the Assured Workloads findings. Do not summarize the section as
"covered" or "ready".

## Questions to put to the user

- Which folders hold regulated workloads, and under which regime?
- Which locations were the workloads created in?
- Does the reviewing identity hold the Assured Workloads reader role on the organization?
- Who is the person that decides what the findings mean for the authorization?
