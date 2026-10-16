# Repository rules, ownership, dependency updates and notifications

Sources read on 2026-10-16 (fetch again before use; tiers and API fields move):

- Protected branches: https://docs.gitlab.com/user/project/repository/branches/protected/ and
  https://docs.gitlab.com/api/protected_branches/
- Approvals: https://docs.gitlab.com/user/project/merge_requests/approvals/ and
  https://docs.gitlab.com/user/project/merge_requests/approvals/rules/
- Push rules: https://docs.gitlab.com/user/project/repository/push_rules/
- Pipelines must succeed: https://docs.gitlab.com/user/project/merge_requests/auto_merge/
- Code Owners: https://docs.gitlab.com/user/project/codeowners/ and
  https://docs.gitlab.com/user/project/codeowners/reference/
- Project settings API: https://docs.gitlab.com/api/projects/
- Webhooks: https://docs.gitlab.com/user/project/integrations/webhooks/ and
  https://docs.gitlab.com/api/project_webhooks/
- Slack app: https://docs.gitlab.com/user/project/integrations/gitlab_slack_application/
- Dependency scanning: https://docs.gitlab.com/user/application_security/dependency_scanning/
- Renovate on GitLab: https://docs.renovatebot.com/modules/platform/gitlab/ and the
  `renovate-bot/renovate-runner` project on gitlab.com

## Contents

- [Tiers at a glance](#tiers-at-a-glance)
- [Branch protection](#branch-protection)
- [Required checks and approvals](#required-checks-and-approvals)
- [Push rules](#push-rules)
- [CODEOWNERS](#codeowners)
- [Dependabot to Renovate or scanners](#dependabot-to-renovate-or-scanners)
- [Webhooks](#webhooks)
- [Slack and other notifications](#slack-and-other-notifications)
- [Templates and other .github files](#templates-and-other-github-files)
- [Settings the importer does not show](#settings-the-importer-does-not-show)

## Tiers at a glance

As read on the date above. Ask which tier the target project has, then re-check the row you need.

| Feature | Tier |
|---|---|
| Protected branches (roles) | Free, Premium, Ultimate |
| Protected branches with users or groups as pushers and mergers | Premium, Ultimate |
| Require Code Owner approval on a protected branch | Premium, Ultimate |
| Code Owners file | Premium, Ultimate |
| Required approval rules | Premium, Ultimate (Free has optional approvals that do not block merging) |
| Push rules | Premium, Ultimate |
| "Pipelines must succeed" | Free, Premium, Ultimate |
| Push mirror | Free, Premium, Ultimate |
| Pull mirror | Premium, Ultimate |
| External status checks | Ultimate |
| Dependency scanning | Ultimate |
| Webhooks, GitLab for Slack app | Free, Premium, Ultimate |
| ID tokens and OIDC | Free, Premium, Ultimate |

When a needed feature is above the project's tier, say so and give the free path in the table
below. Do not hide the gap.

| Need | Free path |
|---|---|
| Block merges without review | Branch protection that allows merges only through merge requests (role-based), plus team habit; there is no enforced approval count |
| Code ownership | Keep a CODEOWNERS file for people to read; nothing enforces it. Use merge request templates with a reviewer checklist |
| Commit message and signing checks | A CI job that checks them, run on every merge request |
| Dependency vulnerability scanning | `osv-scanner` or `trivy fs` in CI |
| Pull mirror | A push mirror from the source of truth, or a scheduled pipeline that fetches |

## Branch protection

The importer maps GitHub branch protection rules (see references/importer.md). Read the result,
then fill gaps. Settings > Repository > Protected branches.

- Default branch and release branches: push "No one" or Maintainers; merge Developers and
  Maintainers (role-based names work on Free; users and groups need Premium).
- Protect release tags too (Settings > Repository > Protected tags).
- Force push stays off.
- Group-level protected branches exist on Premium and Ultimate; use them when many projects share
  rules.

Drafted API call (needs the user's go; confirm the numbers against the API page, where `0` is No
access, `30` Developer, `40` Maintainer):

```sh
glab api --method POST projects/PROJECT_ID/protected_branches \
  -f name=main -F push_access_level=0 -F merge_access_level=40 \
  -F allow_force_push=false -F code_owner_approval_required=true
```

`code_owner_approval_required` is Premium and Ultimate only per the API page; drop it on Free.

## Required checks and approvals

GitHub's "required status checks" are not imported. Recreate them as:

1. A pipeline that runs for every merge request (see references/actions-to-gitlab-ci.md).
2. Settings > Merge requests > Merge checks > "Pipelines must succeed". The page warns this also
   blocks a merge request that has no pipeline, so a `workflow:rules` block that skips merge
   request pipelines makes merging impossible. Turn it on after one passing pipeline exists.

```sh
glab api --method PUT projects/PROJECT_ID \
  -F only_allow_merge_if_pipeline_succeeds=true \
  -F only_allow_merge_if_all_discussions_are_resolved=true \
  -F remove_source_branch_after_merge=true
```

Also in the project settings API: `merge_method` (`merge`, `rebase_merge` or `ff`) for the merge
strategy GitHub offered as merge, rebase, squash. Check the page for the squash setting name.

Approvals: Premium and Ultimate give required approval rules (Settings > Merge requests >
Approvals); Free approvals are optional. Map GitHub's "required reviewers" count to one rule per
group of reviewers. External status checks (calls to outside systems) are Ultimate.

## Push rules

Premium and Ultimate. They run as pre-receive checks. The page lists: commit content, commit
message format, branch name rules, file details, preventing tag removal, and requiring signed
commits ("Reject unsigned commits", which is where the importer maps GitHub's signed-commit rule).
Regular expressions use RE2 and each is limited to 511 characters. Push rules are copied to a
project when it is created and do not follow later group changes. On Free, put the same checks in
a CI job.

## CODEOWNERS

GitLab reads one `CODEOWNERS` file, first found in this order: repository root, `docs/`, `.gitlab/`.
GitHub also allows `.github/CODEOWNERS`; a file there is ignored in GitLab, so move it
(`git mv .github/CODEOWNERS CODEOWNERS`, a draft for the user to approve).

Differences to check on the reference page (https://docs.gitlab.com/user/project/codeowners/reference/):

- Owners are users, groups (`@group`, `@group/subgroup`), email addresses, or roles (`@@maintainer`).
  GitHub `@org/team` entries must map to GitLab groups or users.
- Inline comments are unsupported, and owners named inside a comment are still parsed. Move each
  comment to its own line.
- Later rules win; sections `[Name]` are analysed separately, `^[Name]` makes a section optional,
  `[Name][2]` requires two approvals.
- A file with no matching rule needs no Code Owner approval. A `*` rule at the top covers every
  file.
- Enforcement needs a protected target branch with Code Owner approval turned on (Premium and
  Ultimate).

## Dependabot to Renovate or scanners

GitLab has no Dependabot. Options, free first:

1. **Renovate** (free, open source). Run it as a scheduled GitLab pipeline in a small dedicated
   project that includes the `renovate-bot/renovate-runner` template, or use the hosted Mend
   Renovate app. The runner needs a GitLab access token (`api`, `read_user`, `write_repository`
   scopes per the runner's README; the platform page says at least the Developer role) stored as
   the masked variable `RENOVATE_TOKEN`, and a GitHub token with minimal scope as
   `RENOVATE_GITHUB_COM_TOKEN` so changelog and tag lookups are not rate limited. Limit the bot
   with `--autodiscover-filter` to the team's group. Never fork the runner project, per its README.
   Put `templates/renovate.json` (bundled with this skill) at the repository root.
2. **Scanners in CI** (free): `osv-scanner` and `trivy fs` on every merge request and on a schedule.
   They report; they do not open update merge requests.
3. **GitLab dependency scanning** (Ultimate): report and merge request widget integration. Pick it
   only if the tier is Ultimate. Renovate still does the updating.

Mapping from `.github/dependabot.yml`: each `package-ecosystem` becomes a Renovate manager (the
checklist lists them). `schedule.interval` becomes a Renovate `schedule`. `groups` become
`packageRules` with `groupName`. `registries` become `hostRules` with credentials from CI/CD
variables. `reviewers` and `assignees` need GitLab usernames. The `github-actions` ecosystem has no
meaning after the move. Renovate's recommended base preset is `config:recommended`; check the
Renovate docs for its current name.

Ask first whether the team wants update merge requests at all or only vulnerability alerts.

## Webhooks

GitHub webhooks are not imported. Read them (`gh api repos/OWNER/NAME/hooks --jq '.[].config.url'`
shows URLs only; secrets are not returned), then draft each in GitLab:

```sh
printf '%s' "$HOOK_SECRET" | glab api --method POST projects/PROJECT_ID/hooks \
  -f url=https://example.invalid/hook -F token=@- \
  -F push_events=true -F merge_requests_events=true -F enable_ssl_verification=true
```

The `token` value (the shared secret the receiver checks) comes from the user's password manager,
as for any secret. Attribute names are from the webhooks API page; the event list there is long, so
turn on only the events the receiver uses. Test with the "Trigger a test project webhook" API or
the UI test button. Receivers that parse GitHub payloads need changes: GitLab payloads differ.

## Slack and other notifications

Current method on the pages read: install the **GitLab for Slack app** from the project, group or
instance Settings > Integrations. It gives slash commands and notifications; the Slack workspace
owner must allow the app; on self-managed an administrator turns the integration on first. The
older "Slack notifications" integration is marked deprecated on its page; do not set it up.

Notification content can be limited to broken pipelines, pipeline status changes, chosen branches,
or labels. Send build failures for the default branch to the team channel and keep merge request
chatter off it.

For Slack-side work beyond this (channel setup, message posting), the sibling plugin `team-comms`
covers Slack. Link by name only; do not duplicate it here.

Other GitHub integrations (ticket trackers, chat, status badges, deploy services) are listed under
GitHub Settings > Integrations and Webhooks and GitHub Apps. Make one checklist line per entry.

## Templates and other .github files

| GitHub | GitLab |
|---|---|
| `.github/ISSUE_TEMPLATE/*.md` | `.gitlab/issue_templates/*.md` |
| `.github/PULL_REQUEST_TEMPLATE.md` | `.gitlab/merge_request_templates/Default.md` |
| `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md` | Same files in the repository root |
| `FUNDING.yml` | No equivalent |
| `release.yml`, `labeler.yml`, `stale.yml`, `settings.yml` | Config for GitHub actions or apps; replace the behaviour or drop it |

The template folder names are from general knowledge and were not part of the pages fetched; check
the "description templates" page before moving files.

## Settings the importer does not show

Ask the user to read these from GitHub (reads only) and compare:

- Branch rulesets (the importer page lists branch protection rules only)
- Environments, their reviewers and branch rules
- Deploy keys and GitHub Apps
- Repository, environment and organisation secret NAMES (never values)
- Pages, Packages and Projects boards, Discussions
- Default branch name and merge settings
- Team access and outside collaborators
