# GitHub Actions to .gitlab-ci.yml translation guide

Sources (read 2026-10-16): GitLab's migration page https://docs.gitlab.com/ci/migration/github_actions/ ,
the CI/CD YAML reference https://docs.gitlab.com/ci/yaml/ , predefined variables
https://docs.gitlab.com/ci/variables/predefined_variables/ , job rules
https://docs.gitlab.com/ci/jobs/job_rules/ . Re-fetch the keyword you are about to use; the
column "Basis" says how each row was checked.

Basis codes: **M** = on GitLab's migration page. **Y** = keyword confirmed in the YAML reference
when this guide was written. **K** = general knowledge, confirm in the docs before you rely on it.

## Contents

- [How to translate](#how-to-translate)
- [Workflow triggers](#workflow-triggers)
- [Jobs, steps and runners](#jobs-steps-and-runners)
- [Matrix, services, containers](#matrix-services-containers)
- [Caches, artifacts and job outputs](#caches-artifacts-and-job-outputs)
- [Concurrency](#concurrency)
- [Environments and deployments](#environments-and-deployments)
- [Reusable workflows and composite actions](#reusable-workflows-and-composite-actions)
- [Secrets, tokens and permissions](#secrets-tokens-and-permissions)
- [OIDC to cloud providers](#oidc-to-cloud-providers)
- [Context to predefined variable](#context-to-predefined-variable)
- [Common actions](#common-actions)
- [No direct equivalent](#no-direct-equivalent)
- [Agent skill from GitLab](#agent-skill-from-gitlab)

## How to translate

1. Translate one workflow file at a time. Start from the hardened reference pipeline in the
   `ci-harden` skill (`templates/.gitlab-ci.yml`) and fold the project's jobs into it. Do not copy
   that template here.
2. Write the target pipeline for the end state. GitLab's own planning page says moving old
   configuration over as-is carries its problems with it, so use the move to improve the pipeline.
3. Pin job images by digest where the project already pins action SHAs.
4. Run the new pipeline on a branch and on a merge request before cutover.

## Workflow triggers

| GitHub `on:` | GitLab | Basis |
|---|---|---|
| `push` with `branches` | `rules: - if: $CI_PIPELINE_SOURCE == "push" && $CI_COMMIT_BRANCH == "main"` | M, Y |
| `push` with `tags` | `rules: - if: $CI_COMMIT_TAG` (add a pattern match for version tags) | Y |
| `pull_request` | Merge request pipelines: `if: $CI_PIPELINE_SOURCE == "merge_request_event"` | Y |
| `push` and `pull_request` together | Use the "switch between branch and merge request pipelines" `workflow:rules` block on the YAML `workflow` page to avoid duplicate pipelines | Y |
| `paths` / `paths-ignore` | `rules:changes` | Y |
| `schedule` | A pipeline schedule created in the project (not in YAML) plus `if: $CI_PIPELINE_SOURCE == "schedule"` | Y |
| `workflow_dispatch` | `if: $CI_PIPELINE_SOURCE == "web"`; inputs become `spec:inputs` or variables with `description` and `options` | Y |
| `workflow_call` | An `include:` file or a CI/CD component with `spec:inputs` | Y |
| `workflow_run` | `trigger:` (parent-child or multi-project) or `needs:pipeline` | Y |
| `repository_dispatch` | A trigger token or the pipelines API (`CI_PIPELINE_SOURCE` of `trigger` or `api`) | Y |
| `release`, `create` | Tag pipeline (`$CI_COMMIT_TAG`) | K |
| `pull_request_target` | No equivalent. See [No direct equivalent](#no-direct-equivalent) | K |

Put branch and merge request logic in `workflow:rules` once, then keep job `rules` for job-level
choices. A `rules` entry that is only a condition runs the job; add `when: never` to exclude.

Pitfall: with "Pipelines must succeed" on, a `workflow:rules` block that stops a merge request
pipeline blocks merging (the YAML `workflow` page has the troubleshooting entry).

## Jobs, steps and runners

| GitHub | GitLab | Basis |
|---|---|---|
| `jobs.<id>` | A top-level job key | M |
| `steps` and `run` | `script` (a list; one entry per command) | M |
| `name` on a step | A comment, or split into separate jobs | K |
| `runs-on` | `tags` to choose a runner; `image` for the container | M |
| `container` | `image` | M |
| `needs` | `needs` (adds artifacts passing and order independent of stages) | Y |
| stages order | `stages:` list; jobs without `needs` wait for the previous stage | M |
| `if` on a job | `rules:if` | M |
| `env` | `variables` at top level or in a job | M |
| `timeout-minutes` | `timeout` | Y |
| `continue-on-error` | `allow_failure` | Y |
| `if: always()` | `when: always` | Y |
| `if: failure()` | `when: on_failure` | Y |
| `working-directory` | `cd` in `script`, or set it once in `before_script` | K |
| `defaults.run.shell` | The runner's shell executor setting, or a `bash -c` wrapper | K |

Runners: GitLab.com has shared runners; self-hosted labels need runners registered with matching
tags. The inventory lists the labels that need this.

## Matrix, services, containers

| GitHub | GitLab | Basis |
|---|---|---|
| `strategy.matrix` axes | `parallel:matrix` with variable names (letters, digits, underscore) | M, Y |
| matrix `include` / `exclude` | No keyword in the `parallel:matrix` section of the YAML reference. Write the combinations out as separate matrix entries | Y |
| matrix upper bound | The reference limits permutations per job; check the current number | Y |
| `fail-fast` | No direct keyword; use `allow_failure` or separate jobs | K |
| `services` | `services:` (job or default level) with an `alias` | Y |

Matrix values arrive as environment variables, so `${{ matrix.os }}` becomes `$OS` for an axis
named `OS`.

## Caches, artifacts and job outputs

| GitHub | GitLab | Basis |
|---|---|---|
| `actions/cache` | `cache:` with `key` and `paths` | M |
| `actions/upload-artifact` | `artifacts:` with `paths` and `expire_in` | M |
| `actions/download-artifact` | Later jobs receive earlier artifacts by stage order, or choose them with `needs` / `dependencies` | M, Y |
| Job `outputs` and `$GITHUB_OUTPUT` | A `dotenv` report (`artifacts:reports:dotenv`) read by later jobs through `needs` | Y |
| `$GITHUB_ENV` | `export` in the same job; across jobs use the `dotenv` report | K |
| `$GITHUB_STEP_SUMMARY` | Job log plus a report artifact; there is no summary panel | K |

Cache keys: GitLab's cache is a speed-up and may be missing; artifacts are the hand-off between
jobs. Do not treat a cache hit as a requirement.

## Concurrency

| GitHub | GitLab | Basis |
|---|---|---|
| `concurrency.group` serialising deploys | `resource_group: production` on the deploy job | Y |
| `cancel-in-progress: true` | `interruptible: true` on jobs plus `workflow:auto_cancel:on_new_commit: interruptible` | Y |

Never mark a deploy job `interruptible: true`.

## Environments and deployments

| GitHub | GitLab | Basis |
|---|---|---|
| `environment: production` | `environment:` with `name` and optionally `url`, `action`, `deployment_tier` | Y |
| Environment secrets | CI/CD variables with an environment scope | K |
| Required reviewers | Protected environments with approvals; confirm the tier and settings on the environments page | K |
| Branch restrictions on environments | Protected branches plus protected environments | K |

Cloud deployment templates and the GitLab agent for Kubernetes are named in GitLab's migration
steps (https://docs.gitlab.com/ci/cloud_deployment/ and the Kubernetes agent pages).

## Reusable workflows and composite actions

| GitHub | GitLab | Basis |
|---|---|---|
| Reusable workflow (`workflow_call`) in the same repository | `include: - local: path/to/file.yml` | Y |
| Reusable workflow in another repository | `include: - project: group/project`, `ref:`, `file:` | Y |
| Marketplace-style reuse across the organisation | A CI/CD component in the catalog: `include: - component: host/group/project/name@version` with `spec:inputs` | Y |
| GitLab-provided template | `include: - template: Jobs/SAST.gitlab-ci.yml` style | M |
| Composite action | A hidden job (`.name`) used with `extends`, a YAML anchor, or a component | Y |
| `uses: owner/action@ref` | The tool's CLI in `script`, or an include/component | M |

Inputs: components take `spec:inputs`. Prefer inputs to custom variables so the caller's choices
are visible and validated.

## Secrets, tokens and permissions

| GitHub | GitLab | Basis |
|---|---|---|
| `${{ secrets.NAME }}` | CI/CD variable `NAME`, masked and protected as needed, read as `$NAME` | M, Y |
| `${{ vars.NAME }}` | CI/CD variable (not masked), or `variables:` in YAML for non-secret values | Y |
| `GITHUB_TOKEN` | `CI_JOB_TOKEN` | K |
| `permissions:` | The job token's access: a project allowlist plus fine-grained job token permissions; use a project access token only where the job token cannot do the job | Y |
| Organisation-level secrets | Group-level CI/CD variables | Y |
| File secrets (certificates, key files) | A File type variable: the job gets a path in the variable | Y |

Variable rules from the CI/CD variables page: a masked value must be one line, no spaces, at least
eight characters, and must not match another variable name. Protected variables reach only
protected branches and tags (and merge request pipelines when that option is on).
Masking is not a guarantee; prefer OIDC and an external secrets manager for high-value secrets.

Never write secret values in `.gitlab-ci.yml`. The skill lists secret names and tells the user to
enter values from their password manager (see references/execute-commands.md).

## OIDC to cloud providers

| GitHub | GitLab | Basis |
|---|---|---|
| `permissions: id-token: write` | `id_tokens:` on the job with a named token and an `aud` | Y |
| Token request URL environment variables | The token arrives as the named environment variable | Y |
| `google-github-actions/auth` | `id_tokens:` plus a Security Token Service exchange (script in references/gcp-wif-trust.md) | Y |

## Context to predefined variable

| GitHub | GitLab predefined variable |
|---|---|
| `github.sha` | `CI_COMMIT_SHA` |
| `github.ref_name` | `CI_COMMIT_REF_NAME` |
| `github.head_ref` | `CI_MERGE_REQUEST_SOURCE_BRANCH_NAME` |
| `github.base_ref` | `CI_MERGE_REQUEST_TARGET_BRANCH_NAME` |
| `github.event_name` | `CI_PIPELINE_SOURCE` (values: `push`, `merge_request_event`, `schedule`, `web`, `api`, `trigger`, `pipeline`) |
| `github.repository` | `CI_PROJECT_PATH` |
| `github.workspace` | `CI_PROJECT_DIR` |
| `github.run_id` | `CI_PIPELINE_ID` (pipeline) or `CI_JOB_ID` (job) |
| `github.actor` | `GITLAB_USER_LOGIN` |
| `github.event.pull_request.number` | `CI_MERGE_REQUEST_IID` |
| `github.ref_protected` | `CI_COMMIT_REF_PROTECTED` |
| `github.server_url` | `CI_SERVER_URL` |
| `github.api_url` | `CI_API_V4_URL` |
| Tag ref | `CI_COMMIT_TAG` (set only on tag pipelines) |
| Default branch | `CI_DEFAULT_BRANCH` |
| Container registry image | `CI_REGISTRY_IMAGE`, with `CI_REGISTRY_USER` and `CI_REGISTRY_PASSWORD` for login |

Every variable name in this table was found in the predefined variables page on the read date.
Expression functions (`contains`, `startsWith`, `format`) have no counterpart; use shell tests in
`script` or regular-expression matches in `rules:if`.

## Common actions

The inventory script prints a hint for each action it finds. The standing ones:

| Action | In GitLab |
|---|---|
| `actions/checkout` | Done by the runner before `script`. Set `GIT_DEPTH`, `GIT_STRATEGY` or `GIT_SUBMODULE_STRATEGY` if the step set fetch depth or submodules |
| `actions/setup-node`, `setup-python`, `setup-go`, `setup-java` | A job `image:` that carries the toolchain |
| `docker/login-action` | `docker login` with `CI_REGISTRY_*` |
| `docker/build-push-action` | The image build job from `ci-harden`; signing is in `image-supply-chain` |
| `google-github-actions/*` | `gcloud` in `script` after the token exchange |
| `github/codeql-action` | Semgrep CE in a job, or GitLab SAST if the tier includes it |
| `softprops/action-gh-release` | `release:` keyword or `glab release create` |
| `aquasecurity/trivy-action`, `gitleaks/gitleaks-action` | The CLI in `script`; the same tools |
| `dependabot/fetch-metadata` | Not needed; see Renovate in references/repo-settings.md |

## No direct equivalent

- `pull_request_target`: it runs trusted code with secrets on untrusted fork input. GitLab has no
  trigger with that meaning. Decide how fork merge requests are tested (the project setting for
  running pipelines in the parent project, with protected variables kept away from forks) and
  review each such workflow with a person.
- Workflow commands (`::error::`, `::add-mask::`): use plain log output and masked variables.
- Job summaries and check-run annotations: use report artifacts shown in merge requests.
- Scripts that call `gh`: rewrite with `glab` or the GitLab API.
- `actions/github-script`: rewrite against the GitLab API.
- Bots such as stale-issue and labeler actions: a scheduled pipeline job or a triage tool.

## Agent skill from GitLab

GitLab's migration page points to "GitHub Actions to GitLab CI/CD agent skill"
(https://about.gitlab.com/github-actions-to-gitlab-ci/ , source
https://gitlab.com/gitlab-org/ci-cd/github-actions-to-gitlab-ci). It was not read or run while
writing this guide. If the user wants it, review its files before use (third-party material),
and treat its output as a draft to compare against the table above.
