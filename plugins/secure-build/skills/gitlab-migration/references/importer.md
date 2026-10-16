# GitLab GitHub importer: what moves, what does not, how to run it

Facts below were read from the GitLab documentation on 2026-10-16. Fetch the importer page again
before relying on any of it: https://docs.gitlab.com/user/project/import/github/ . A self-managed
instance can be older than the public pages, so also read `https://<host>/help/user/project/import/github`
on that instance and note any difference.

## Contents

- [Imported by the importer](#imported-by-the-importer)
- [Not carried over](#not-carried-over)
- [Branch protection mapping](#branch-protection-mapping)
- [Collaborator role mapping](#collaborator-role-mapping)
- [Ways to run the import](#ways-to-run-the-import)
- [Drafted API command](#drafted-api-command)
- [User mapping and placeholder users](#user-mapping-and-placeholder-users)
- [Rate limits and duration](#rate-limits-and-duration)
- [Checking, cancelling and repeating](#checking-cancelling-and-repeating)
- [Known issues from the page](#known-issues-from-the-page)

## Imported by the importer

The "Imported data" list on the page names these items:

- All project branches, and fork branches tied to open pull requests (named like
  `GH-SHA-username/pull-request-number/fork-name/branch`)
- Git repository data and Git LFS objects
- Issues, pull requests (merge requests), labels, milestones
- Issue and pull request comments, and issue and pull request events
- Pull request reviews, review comments, review replies, review suggestions, assigned reviewers,
  and "merged by" information
- Release notes content and repository descriptions
- Wiki pages
- Attachments for comments, issue descriptions, pull request descriptions and release notes
  (off by default; see below)
- Branch protection rules (mapped, see below)
- Collaborators as members (on by default in the UI)

References to pull requests and issues are kept. Visibility is kept unless the instance restricts
that level, in which case the default project visibility applies. Imported items carry an
"Imported" badge in GitLab.

Optional items the UI leaves off by default: Markdown attachments. Turning them on can add a lot
of time. API optional stages named in the API page: `attachments_import`, `collaborators_import`
and `single_endpoint_notes_import`. Read the API page for which of them your instance requires.

## Not carried over

Two groups. Keep them apart in the plan.

Stated on the page as not imported or limited:

- The "Require status checks to pass before merging" rule. Recreate it as "Pipelines must succeed"
  (see references/repo-settings.md).
- GitHub organizations and groups. The importer moves projects only.
- Custom repository roles on GitHub Enterprise Cloud. They cause partially completed imports.
- Reviewers and approvals when the person has no matching GitLab user; the importer leaves a
  comment instead and does not apply the reviewer or approval state.
- Markdown attachments from GitHub Enterprise Server instances on older GitLab versions; on newer
  versions only video and image files import. The page gives the exact versions.
- Pull request comments written before 2017 arrive as separate threads (GitHub API limit).
- Mirroring does not sync later pull requests or issues.

Not on the page's imported list. Treat each as not imported and confirm after the import. The page
does not say "not imported" for these; the list simply does not contain them:

- GitHub Actions workflows (the files copy as ordinary repository files; they do nothing in GitLab),
  run history, artifacts, caches, self-hosted runners
- Secrets and variables (repository, environment and organization level)
- Webhooks, deploy keys, GitHub Apps and other integrations
- Dependabot configuration and alerts (the config file copies as an ordinary file)
- GitHub Projects boards, Discussions, Pages sites
- GitHub Packages and container images in ghcr.io
- Rulesets (the page lists branch protection rules only)
- Environments and their reviewers

## Branch protection mapping

From the importer page:

| GitHub rule | GitLab result |
|---|---|
| Require conversation resolution before merging (default branch) | "All threads must be resolved" project setting |
| Require a pull request before merging | "No one" in "Allowed to push and merge" |
| Require signed commits (default branch) | "Reject unsigned commits" push rule |
| Allow force pushes: Everyone | "Allowed to force push" on the protected branch |
| Require review from Code Owners | "Require approval from code owners" on the protected branch |
| Allow specified actors to bypass required pull requests | Users in "Allowed to push and merge"; without Premium the list is limited to roles |

Check the result in Settings > Repository > Protected branches after the import. The push-rule
row needs a tier that has push rules (see references/repo-settings.md).

## Collaborator role mapping

| GitHub | GitLab |
|---|---|
| Read | Guest |
| Triage | Reporter |
| Write | Developer |
| Maintain | Maintainer |
| Admin | Owner |

The importer reads collaborators only when the person running it has Write or Maintain on the
GitHub project; otherwise that step is skipped. Only direct collaborators come across, never
outside collaborators. Importing collaborators can use seats and grant high roles, so review the
member list afterwards.

## Ways to run the import

Prerequisites on the page: the GitHub import source is enabled (on by default on GitLab.com; an
administrator enables it on self-managed), the person has access to the source project, and has the
Maintainer or Owner role on the destination group. The GitHub organization must not block
third-party application access for the GitLab instance.

| Method | Use when | Notes |
|---|---|---|
| UI with GitHub OAuth | GitLab.com, or self-managed with GitHub OAuth configured | The token never leaves the browser flow |
| UI with a personal access token | Default for github.com sources | Classic tokens only. Scope `repo`; add `read:org` for collaborators or LFS |
| REST API `POST /import/github` | GitHub Enterprise Server sources, `timeout_strategy`, importing public repos you do not own | Needs a GitLab personal access token with the `api` scope; the UI always uses the github.com domain |
| `glab` | No dedicated import command exists in the glab version checked. Use `glab api` | See the drafted command |

The person who owns the GitHub token types it themselves. Claude never asks for it and never
receives it.

## Drafted API command

Show this as a draft. Run nothing until the user says go for this step. Ask the user to run the
import in their own terminal, so the GitHub token is typed at a silent prompt and never enters the
conversation.

First, read-only lookups Claude may run: the numeric GitHub repository ID, and the target group.

```sh
gh api repos/OWNER/NAME --jq .id
glab api groups/GROUP%2FSUBGROUP --jq .full_path
```

Then the import (placeholders are in capitals; nothing secret appears in the command text):

```sh
read -rs GH_PAT                       # type or paste the GitHub token; nothing is echoed
printf '%s' "$GH_PAT" | glab api --method POST import/github \
  -F personal_access_token=@- \
  -F repo_id=GITHUB_REPO_ID \
  -f target_namespace=GROUP/SUBGROUP \
  -f new_name=PROJECT_NAME \
  -F 'optional_stages={"attachments_import":true,"collaborators_import":true}'
unset GH_PAT
```

How the flags behave (from `glab api --help` in the version checked): `-F key=@-` reads the value
from standard input; `-F` turns integers and JSON objects into the matching JSON types; `-f` sends
a string. For a self-managed GitLab add `--hostname GITLAB_HOST`. For GitHub Enterprise Server add
`-f github_hostname=https://GHES_HOST`. Remove an optional stage you do not want.

The REST API accepts GitLab personal access tokens only, per the page. Whether a `glab` login made
with OAuth is accepted by this endpoint was not verified; if the call is refused, log in with a
personal access token (`glab auth login --stdin`, token piped from the password manager) or use the
UI.

Optional API fields from the API page: `pagination_limit` (smaller values reduce 500 and 502
errors from GitHub on large repositories, and lengthen the import) and `timeout_strategy`
(`optimistic` continues to the next stage on timeout; `pessimistic`, the default, fails at once).

## User mapping and placeholder users

The importer uses post-migration mapping. Read the page "Post-migration contribution and
membership mapping" (https://docs.gitlab.com/user/import/mapping/post_migration_mapping/).

- Contributions and memberships are first assigned to placeholder users, even when a GitLab user
  with the same email exists. A placeholder cannot sign in, run pipelines or be a member.
- After the import, the group Owner reassigns each placeholder to a real user (Manage > Members >
  Placeholders tab, top-level group). The person can accept or reject the reassignment.
- Placeholders are tied to the top-level group. Use a designated top-level group for a test import;
  deleting that group schedules its placeholders for removal.
- Importing to a personal namespace skips mapping: everything goes to the namespace owner and
  cannot be reassigned.
- A placeholder user limit exists; contributions beyond it map to an import user. Read the limits
  section of that page before a large import.
- Enterprise users: if the top-level group has any, reassignment is limited to them.

Plan: list GitHub contributors, decide who maps to whom, and schedule the reassignment before
people start reviewing merge requests.

## Rate limits and duration

- GitHub API requests are normally limited to 5,000 per hour per token. On self-managed with a
  GitHub Enterprise Cloud OAuth app the page says 15,000 per hour is possible.
- The page reports a very large repository (80,000 pull requests, 45,000 issues) taking about
  three days. Size the freeze window from the item counts (issues, pull requests, comments).
- Self-managed administrators can add Sidekiq workers for the `github_importer` queues; cloning
  time does not shrink with more workers.

## Checking, cancelling and repeating

- Status in the UI: Complete, Partially completed, Failed. Open Details for failed entities.
- Status by API (read-only): `glab api projects/PROJECT_ID/import` returns `none`, `scheduled`,
  `failed`, `started` or `finished`, and `import_error` when failed.
- Cancel: UI Cancel button, or `POST /import/github/cancel` with `project_id`. Files already
  imported stay.
- Re-import: creates a new copy under a new name. It does not update the first one.
  For catching up after the freeze, use a push or pull mirror for Git data (see
  references/cutover-and-rollback.md); issues and merge requests need a fresh import.

## Known issues from the page

- Auto-merge commits signed by GitHub's internal key can show as unverified.
- Markdown image attachments uploaded to private repositories before 2023-05-09 cannot import.
- `#123` references: GitLab uses `#` for issues and `!` for merge requests. In comments only issue
  links are created; descriptions get no links.
- With SAML single sign-on on the GitHub organization, attachments can fail. The page's workaround
  is to add the importing GitLab user as an outside collaborator on the GitHub repository.
- Username mentions are wrapped in backticks so they cannot link to a different GitLab user.
