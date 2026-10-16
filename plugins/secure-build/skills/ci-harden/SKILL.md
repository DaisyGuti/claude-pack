---
name: ci-harden
description: >-
  Audits and hardens CI/CD pipelines on GitHub Actions and GitLab CI, and ships two reference
  pipelines that build, scan, write SBOMs, sign and push an image to Google Artifact Registry
  with Workload Identity Federation. GitHub checks: actions pinned to full commit SHAs,
  least-privilege permissions, risky pull_request_target use, script injection, OIDC to GCP
  instead of service-account JSON keys, environment protection, CODEOWNERS, branch protection,
  Dependabot or Renovate, zizmor. GitLab checks: protected branches and variables, masked
  variables, id_tokens for GCP, images and includes pinned, runner isolation, security scanning
  templates (which tiers need Ultimate, and the free alternatives). Use it for "review our
  workflow", "harden our pipeline", "secure our CI", "pin our actions", "remove the GCP key from
  CI", "set up keyless auth to GCP", "write a secure build pipeline", ".gitlab-ci.yml review",
  or any CI/CD security question, even if the user does not mention hardening. For Dockerfile
  edits use dockerfile-harden; for image signing details use image-supply-chain. To review the
  Google Cloud side (IAM bindings, Workload Identity pools, organization policies), use
  gcp-review.
allowed-tools: >-
  Read Grep Glob Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/*) Bash(zizmor *) Bash(uvx zizmor *)
  Bash(glab ci lint *)
---

# Hardening GitHub Actions and GitLab CI pipelines

Find what is unsafe in the pipeline files, fix it in the files, and draft the settings changes
that live in the platform. Reading settings is free; changing them is for the user to run.

## Steps

1. **Find the pipelines.** Glob for `.github/workflows/*.yml|yaml` and `.gitlab-ci.yml` (plus
   `*.gitlab-ci.yml` includes). Say which platform or platforms are present. Read every file in
   full before judging it.
2. **Run the deterministic audit.** Execute (do not read) the bundled script:

   ```sh
   python3 ${CLAUDE_SKILL_DIR}/scripts/ci_audit.py <repo-dir-or-file> ...
   ```

   Findings carry an id (`GHA###`, `GLC###`, `CI###`), a line and a fix. It is line-based, so a
   clean result covers the obvious rules only.
3. **Run the fuller linter when it is installed.** For GitHub Actions run
   `zizmor .` (or `uvx zizmor .`; check with `command -v zizmor uvx`). Use `--persona pedantic`
   for a deep pass and `--offline` when there is no token. For GitLab run `glab ci lint` against
   the file (it needs a signed-in `glab`; the output is a syntax check only).
   When a tool is missing, say so in the report; do not install it.
4. **Read live settings, read-only.** The commands are in `references/github-actions.md` (`gh api`
   on actions permissions, rulesets, environments) and `references/gitlab-ci.md` (protected
   branches, variables). Skip any you lack access for and list them under *Not checked*.
5. **Fix the files.** Apply the mechanical fixes directly: pin actions (resolve each SHA with
   `gh api`, never from memory), add `permissions: {}` and per-job grants, move untrusted
   expressions into `env:`, replace key-file cloud auth with Workload Identity Federation, pin
   images and includes. Ask before any change that alters what the pipeline does, such as
   removing a job or tightening a trigger.
6. **New pipeline?** Start from `templates/.github/workflows/secure-build.yml` or
   `templates/.gitlab-ci.yml`, fill in the variables their header lists, and keep the structure.
   Both pass `ci_audit.py` and the GitHub file passes `zizmor` and `actionlint`.
7. **Draft the cloud and platform steps.** The pool, provider, service account and Artifact
   Registry commands are in `references/gcp-workload-identity.md`; branch protection, environments
   and CODEOWNERS are in the platform references. Show each with its placeholders and wait for
   the user to run it. Never run a command that creates, updates or deletes cloud or platform state.
8. **Verify.** Re-run `ci_audit.py` and `zizmor`. A run of the real pipeline on a scratch branch
   is the only proof the authentication works; ask the user to do it and read the job logs.
9. **Report** under *Fixed* (id, file, one line), *Drafted* (commands awaiting the user),
   *Still open* (with the reason and the decider) and *Not checked*.

## Decisions to put to the user

- **Signing visibility.** Keyless signatures are recorded in Sigstore's public transparency log
  and carry the repository or project path. See `image-supply-chain/references/sign-and-attest.md`
  and offer the KMS-key alternative.
- **Plan limits.** GitHub environments, rulesets and artifact attestations on private repositories
  depend on the plan. GitLab Code Owners, protected environments and Ultimate scanners depend on
  the tier. State the limit and the free fallback in the references; ask which plan the team has
  when it matters.
- **Scan gate.** The severity that fails a build, and whether unfixed findings count.
- **Runner model.** Where publish jobs run and who else can run jobs there.

## Rules

- Evidence and fixes only. Never state that a pipeline or system is compliant or authorized.
- A rule that must hold on every commit belongs in a protected-branch setting, a required status
  check or a hook, because advice in this skill can be skipped. Say so when proposing a rule.
- Fetch moving facts at run time: action SHAs and versions, tool digests and checksums,
  GitHub and GitLab tier statements. The references list their sources and when they were read.
- Never put a secret value in chat, in a file or in a log. The reference pipelines need
  identifiers only.

## Related skills

- Scanning the source, dependencies and history for secrets: `security-scan` in the `security` plugin.
- What the image steps do and how signatures are verified: `image-supply-chain`.
- Moving a repository and its pipelines from GitHub to GitLab: `gitlab-migration`.
- Reviewing the GCP project the pipeline deploys to: `gcp-review`.

## Tools

`python3` 3.11+ (bundled script), optional `zizmor`, `actionlint`, `gh`, `glab`, `gcloud`. Check
each with `command -v <tool>`. All free and open source.

## References

- `references/github-actions.md`: GitHub rules, zizmor, repository settings, dependency bots.
- `references/gitlab-ci.md`: GitLab rules, tiers, protected refs, runners, scanning templates.
- `references/gcp-workload-identity.md`: pool, provider, service account and bindings for both hosts.

Templates: `templates/.github/workflows/secure-build.yml`, `templates/.gitlab-ci.yml`,
`templates/dependabot.yml`, `templates/renovate.json`, `templates/CODEOWNERS`.
