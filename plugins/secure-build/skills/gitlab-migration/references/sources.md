# Sources, fetch dates and what was verified

All pages were fetched on 2026-10-16. Pages marked "re-fetch" are the ones the skill must read
again when it runs, because the facts on them change with GitLab releases. When a self-managed
instance is older than the public pages, read the copy shipped on the instance
(`https://<host>/help/...`) and prefer it.

## Contents

- [Pages read](#pages-read)
- [Verified against the pages](#verified-against-the-pages)
- [Not verified](#not-verified)
- [Local tool help read](#local-tool-help-read)

## Pages read

| Topic | URL | Re-fetch at run time |
|---|---|---|
| GitHub importer | https://docs.gitlab.com/user/project/import/github/ | yes |
| Import API (`POST /import/github`) | https://docs.gitlab.com/api/import/ | yes |
| Contribution and membership mapping | https://docs.gitlab.com/user/import/mapping/post_migration_mapping/ | yes |
| Migrate from GitHub Actions | https://docs.gitlab.com/ci/migration/github_actions/ | yes |
| Plan a CI/CD migration | https://docs.gitlab.com/ci/migration/plan_a_migration/ | no |
| CI/CD YAML reference | https://docs.gitlab.com/ci/yaml/ | the keyword in use |
| Workflow rules | https://docs.gitlab.com/ci/yaml/workflow/ | when writing triggers |
| Job rules and pipeline sources | https://docs.gitlab.com/ci/jobs/job_rules/ | when writing triggers |
| Predefined variables | https://docs.gitlab.com/ci/variables/predefined_variables/ | when mapping contexts |
| CI/CD variables (masking, protecting, File type) | https://docs.gitlab.com/ci/variables/ | yes |
| ID tokens (OIDC claims) | https://docs.gitlab.com/ci/secrets/id_token_authentication/ | yes |
| GitLab OIDC with Google Cloud | https://docs.gitlab.com/ci/cloud_services/google_cloud/ | yes |
| Job token (allowlist, permissions) | https://docs.gitlab.com/ci/jobs/ci_job_token/ and https://docs.gitlab.com/ci/jobs/fine_grained_permissions/ | when translating `permissions:` |
| Resource groups | https://docs.gitlab.com/ci/resource_groups/ | no |
| CI/CD components | https://docs.gitlab.com/ci/components/ | when translating reusable workflows |
| Protected branches | https://docs.gitlab.com/user/project/repository/branches/protected/ | yes |
| Protected branches API | https://docs.gitlab.com/api/protected_branches/ | yes |
| Approvals | https://docs.gitlab.com/user/project/merge_requests/approvals/ | yes |
| Push rules | https://docs.gitlab.com/user/project/repository/push_rules/ | yes |
| Pipelines must succeed | https://docs.gitlab.com/user/project/merge_requests/auto_merge/ | no |
| Code Owners and syntax | https://docs.gitlab.com/user/project/codeowners/ and .../codeowners/reference/ | yes |
| Projects API (merge settings) | https://docs.gitlab.com/api/projects/ | yes |
| Webhooks and webhooks API | https://docs.gitlab.com/user/project/integrations/webhooks/ and https://docs.gitlab.com/api/project_webhooks/ | no |
| GitLab for Slack app | https://docs.gitlab.com/user/project/integrations/gitlab_slack_application/ | yes |
| Repository mirroring | https://docs.gitlab.com/user/project/repository/mirror/ (push, pull) | yes |
| Dependency scanning | https://docs.gitlab.com/user/application_security/dependency_scanning/ | no |
| Renovate and GitLab | https://docs.renovatebot.com/modules/platform/gitlab/ , https://docs.renovatebot.com/config-presets/ , `renovate-bot/renovate-runner` README on gitlab.com | yes |
| Google: federation with deployment pipelines | https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines | yes |
| Google: `create-oidc` reference | https://docs.cloud.google.com/sdk/gcloud/reference/iam/workload-identity-pools/providers/create-oidc | yes |

Where the rendered site and the GitLab source repository both exist, the source Markdown
(`doc/` in https://gitlab.com/gitlab-org/gitlab) was read for exact wording. That is the newest
text and can describe versions later than a given instance.

## Verified against the pages

- The importer's imported-data list, the branch protection mapping table, the collaborator role
  table, the token scopes (`repo`, optional `read:org`, classic tokens only), the rate limits and
  the Maintainer or Owner requirement on the destination group.
- The statement that required status checks are not imported.
- The import API fields: `personal_access_token`, `repo_id`, `target_namespace`, `github_hostname`,
  `new_name`, `optional_stages`, `pagination_limit`, `timeout_strategy`; and the cancel endpoint.
- Placeholder users, reassignment and the top-level group scoping.
- Masking rules (one line, no spaces, eight characters, no clash with a variable name), the
  protected and File type variable behaviour.
- `id_tokens` with `aud`, the ID token claims named in the Google reference, and the Google
  Cloud token exchange steps.
- Google: the pool and provider `gcloud` commands, the flags on the `create-oidc` page, and the
  attribute condition requirement for GitLab.com.
- Tiers for protected-branch users and groups, Code Owners, approval rules, push rules, pull
  mirrors, push mirrors, external status checks, dependency scanning, webhooks and the Slack app.
- CODEOWNERS locations, no inline comments, sections.
- Predefined variable names used in the context table; keyword existence for `needs`, `services`,
  `environment`, `parallel:matrix`, `rules`, `extends`, `trigger`, `resource_group`,
  `interruptible`, `id_tokens`, `include:component`, `workflow:auto_cancel`.
- The `parallel:matrix` section lists no `include` or `exclude` keys.

## Not verified

- Whether a `glab` login made with OAuth is accepted by `POST /import/github` (the page says the
  REST API takes personal access tokens).
- Protected environments and deployment approvals: tier and settings were not read.
- The exact `google.subject` length limit and whether `sub` claims exceed it (Google's attribute
  mapping page was not read).
- The `.gitlab/issue_templates` folder name (the merge request template folder name appears in
  `glab mr create --help`).
- Whether GitLab's GitHub Actions agent skill is safe or complete: it was not read.
- Whether an organisation policy on the Google side restricts external identity providers.
- Any behaviour of a GitLab version other than the public pages describe.
- Renovate manager names in the mapping table (from general knowledge).

## Local tool help read

`glab` and `gh` were queried with `--help` only; no API call or repository was touched. Commands
used in drafts come from that output: `glab api` (`--method`, `-f`, `-F`, `--input`, `--hostname`),
`glab variable set/update/list` (`-m`, `-p`, `--hidden`, `-s`, `-t`, `-R`), `glab repo create`,
`glab repo mirror`, `glab repo update --archive`, `glab mr create`, `glab auth login --stdin`,
`gh repo archive`, `gh repo edit`, `gh api`.
