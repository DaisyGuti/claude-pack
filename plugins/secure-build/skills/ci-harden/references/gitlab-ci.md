# Hardening GitLab CI

Contents:
- The rules the audit script checks
- Which features need which tier
- Protected branches, tags, variables and environments
- Images, includes and tools
- Runners
- OIDC to Google Cloud
- GitLab security scanning templates and the free alternatives
- Keeping pins current
- Sources

## The rules the audit script checks

`scripts/ci_audit.py` reports these ids for `.gitlab-ci.yml` and `*.gitlab-ci.yml` files.

| Id | Finding |
|---|---|
| GLC001 | `image:` or a service image not pinned by digest (info when the image is a variable) |
| GLC002 | `include:` of a `remote:` URL, a `project:` without a commit-SHA `ref:`, or a component without a fixed version |
| GLC003 | Long-lived cloud credentials: key variables, `activate-service-account --key-file` |
| GLC004 | A literal secret-looking value in `variables:` |
| GLC006 | `CI_DEBUG_TRACE: "true"` |
| GLC007 | `allow_failure: true` on a scan, secret detection, lint or verify job |
| GLC009 | A bare `env`, `printenv` or `set` line in a script |
| GLC010 | `docker:dind`, which needs a privileged runner |
| GLC012 | Google Cloud calls with no `id_tokens:` |
| CI001, CI002, CI003 | Pipe-to-shell installs, `docker login -p`, private keys and cloud access keys written into the file |

## Which features need which tier

Read 2026-10-16 from the GitLab documentation; re-check the page for the tier before telling a
user a control is available.

| Control | Tier | Free alternative |
|---|---|---|
| Protected branches and tags (roles) | Free, Premium, Ultimate | none needed |
| Naming users and groups on branch protection, Code Owner approval | Premium, Ultimate | A second reviewer by convention; a pipeline job that fails when `.gitlab-ci.yml` changes without a listed reviewer |
| Code Owners | Premium, Ultimate | none; keep the file for documentation |
| Protected environments (deployment approvals) | Premium, Ultimate | Protected branches plus a Workload Identity condition on `ref_protected` |
| Masked and hidden CI/CD variables, protected variables | Free and above | none needed |
| Environment-scoped group variables | Premium, Ultimate | Project variables, protected |
| SAST, secret detection | Free, Premium, Ultimate. Free and Premium produce a downloadable JSON report. Merge request findings and the vulnerability report need Ultimate. Advanced SAST needs Ultimate | `semgrep` CE, `gitleaks`, trivy in a job; the `security` plugin covers source scans |
| Container scanning | Free, Premium, Ultimate. It uses Trivy. Free and Premium produce a JSON report and a CycloneDX SBOM. Merge request presentation, allowlisting and auto-remediation need Ultimate. The Grype analyzer is deprecated | trivy in a job, as in the reference pipeline |
| Dependency scanning | Ultimate | `osv-scanner` or trivy `fs` in a job |

## Protected branches, tags, variables and environments

- Protect the default branch (it is protected by default) and the release tag pattern `v*`.
  Allow merges through merge requests and set "Allowed to push and merge" to No one.
- Make deploy-capable variables **protected** (available only on protected branches and
  tags) and **masked** when they hold a secret (single line, at least 8 characters). Prefer
  "masked and hidden" for anything that must never be shown in settings. The reference pipeline
  needs no secret variables, only identifiers.
- Variables and code that publish should run only on protected refs. A merge request pipeline
  from an unprotected branch must not see them.
- Use `environment:` for deployments. Protecting an environment needs Premium; on Free, the
  Workload Identity attribute condition on `ref_protected` does the same job for cloud access.
- Limit what `CI_JOB_TOKEN` can reach with the project's job token allowlist
  (https://docs.gitlab.com/ci/jobs/ci_job_token/).

## Images, includes and tools

- GitLab's pipeline security guidance: always use SHA digests for Docker images, avoid variables
  in container references, pin `include:` to a specific ref and prefer storing included files in
  the repository, and lock package dependencies with exact versions and hashes.
- Pin images as `name:tag@sha256:...` and let Renovate move them. `GLC001` finds the rest.
- A job that downloads a tool pins its URL, version and SHA-256 and verifies the checksum
  before running it (the reference pipeline does this for trivy, syft and cosign). Renovate
  bumps image digests; it does not recompute a checksum, so the pinned binaries are bumped by
  hand or by a small scripted update, each time reading the project's published checksums file.
- Images that ship without a shell (syft, cosign) cannot run a `script:`. Download the release
  binary into a pinned base image as the reference pipeline does.

## Runners

- Use ephemeral runners, scoped to the project or group, for any job that can reach the cloud.
  Do not run publish jobs on a runner shared with untrusted merge requests.
- Docker-in-Docker needs a privileged runner. The reference pipeline avoids it: rootless
  BuildKit builds the image. On self-managed Docker-executor runners that do not run
  privileged, rootless BuildKit may need the executor's `security_opt` adjusted; GitLab's
  BuildKit page explains the setting.
- Pin the runner version and keep it patched.

## OIDC to Google Cloud

Declare `id_tokens:` with an `aud`, exchange the token at Google's Security Token Service, and
impersonate a service account; the reference pipeline's `.gcp_login` block does exactly this.
Create the pool, provider and condition from `gcp-workload-identity.md`, which restricts access
to one project ID and to protected refs. The claims available in the token (`project_id`,
`project_path`, `ref`, `ref_protected`, `environment`, `ci_config_ref_uri` and others) are listed
on GitLab's ID token page.

## GitLab security scanning templates and the free alternatives

```yaml
include:
  - template: Jobs/SAST.gitlab-ci.yml
  - template: Jobs/Secret-Detection.gitlab-ci.yml
  - template: Jobs/Container-Scanning.gitlab-ci.yml   # set CS_IMAGE to the pushed digest
```

On Free and Premium these jobs run and write JSON reports as job artifacts; the merge request
widget and vulnerability report need Ultimate. Read the report artifact in a follow-up job or
download it. `template:` includes are versioned with the GitLab instance; they cannot be pinned
to a commit, so note the instance version in the audit report. Secret detection and container
scanning have `-fips` analyzer image variants selectable by variable; fetch the page for the
variable name before using one.

## Keeping pins current

Copy `templates/renovate.json`. Its `gitlabci` manager updates `image:` digests in
`.gitlab-ci.yml`, and `config:best-practices` pins Docker digests and delays new releases with
`minimumReleaseAge`. Run Renovate from a scheduled pipeline with the project's own token, or use
a hosted Renovate app. GitLab does not run Dependabot.

## Sources

Fetched 2026-10-16.

- Pipeline security: https://docs.gitlab.com/ci/pipeline_security/
- CI/CD variables: https://docs.gitlab.com/ci/variables/
- Protected branches: https://docs.gitlab.com/user/project/repository/branches/protected/
- Protected environments: https://docs.gitlab.com/ci/environments/protected_environments/
- Code Owners: https://docs.gitlab.com/user/project/codeowners/
- ID token claims: https://docs.gitlab.com/ci/secrets/id_token_authentication/
- GitLab and Google Cloud: https://docs.gitlab.com/ci/cloud_services/google_cloud/
- Keyless signing examples: https://docs.gitlab.com/ci/yaml/signing_examples/
- Building images, rootless BuildKit: https://docs.gitlab.com/ci/docker/using_buildkit/ and https://docs.gitlab.com/ci/docker/using_docker_build/
- SAST: https://docs.gitlab.com/user/application_security/sast/
- Secret detection: https://docs.gitlab.com/user/application_security/secret_detection/pipeline/
- Container scanning: https://docs.gitlab.com/user/application_security/container_scanning/
- Dependency scanning: https://docs.gitlab.com/user/application_security/dependency_scanning/
- Job token: https://docs.gitlab.com/ci/jobs/ci_job_token/ (listed by the `gitlab-migration` skill; not re-read here)
