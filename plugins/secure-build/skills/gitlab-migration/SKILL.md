---
name: gitlab-migration
description: Plans a move of a repository from GitHub to GitLab (gitlab.com or self-managed) and, only on the user's explicit go for each step, carries it out. Inventories a local checkout (workflows, Dependabot, CODEOWNERS, secret names, submodules, LFS, hard-coded GitHub URLs), explains what GitLab's GitHub importer carries over and drops, translates GitHub Actions to .gitlab-ci.yml, moves secrets to masked and protected CI/CD variables, re-points Google Cloud Workload Identity Federation at GitLab, maps branch protection, approvals and CODEOWNERS, replaces Dependabot, and writes a cutover and rollback checklist. Use when someone asks to migrate, move or switch from GitHub to GitLab, convert GitHub Actions workflows, replace Dependabot, update Workload Identity trust for GitLab, or plan a mirror period, even if they do not name the importer or say migration.
argument-hint: "[plan|execute] [path to local checkout]"
allowed-tools: Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/*)
---

# GitHub to GitLab migration

Arguments given: $ARGUMENTS

Two modes. **PLAN** is the default: read-only, produces an inventory, a written plan and a
cutover checklist. **EXECUTE** runs only when the user asks for it, and even then each side
effect is drafted, shown, and run only after the user says go for that step.

## Rules that hold in every mode

1. **Reads run freely. Writes wait for a go.** A write is anything that creates, changes, pushes,
   imports, archives or deletes on GitHub, GitLab or Google Cloud, or changes files outside the
   scratch area. Draft it, show it (what it does, where it writes, how to undo it), and stop.
   A go applies to the step just shown.
2. **Second confirmation for removals and replacements.** Archiving the GitHub repository,
   removing the GitHub trust in Google Cloud, replacing an existing GitLab variable: after the
   first go, the user must reply with the exact phrase listed in references/execute-commands.md.
   This skill never drafts a deletion of a GitHub repository, secret or branch; the user does those
   themselves.
3. **Secrets: names only.** List secret names. Never ask for a value, never print one, never write
   one to a file or a command line. The user types each value at a silent prompt in their own
   terminal or pipes it from their password manager (references/execute-commands.md, secrets
   protocol). Do not run `glab variable get`, `glab variable export`, `env` or `printenv`. If the
   user pastes a secret into chat, do not repeat it and tell them to revoke and replace it.
4. **Fetch current facts at run time.** Importer limits, tiers, API fields, OIDC claims and gcloud
   flags change. Before relying on a fact, fetch the page named in references/sources.md and
   say the fetch date in the plan. On self-managed GitLab, prefer the documentation on the
   instance (`https://<host>/help`). The references record what was true when they were written.
5. **Be honest about tiers.** Code Owners, required approvals, push rules and pull mirrors need
   Premium or higher. When the target tier lacks a feature, say so and give the free path
   (references/repo-settings.md).
6. **Evidence and gaps.** The plan lists what moves, what does not, and what needs a person. It never
   states that the new setup is compliant, authorized or ready. Whether the target host is allowed
   for the product's data and environment is for the team's security owner to decide; ask who that
   is and put the question in the plan.
7. **`allowed-tools` only pre-approves.** It lets the bundled scripts run without a prompt and
   restricts nothing, so rules 1 to 3 are Claude's own discipline.

## Collect inputs (ask once, in one message)

- GitHub source: `OWNER/NAME`, github.com or GitHub Enterprise Server, path to a local checkout.
- GitLab target: gitlab.com or the self-managed URL; target group and project path; tier if known.
- Who owns cutover; target window; how long outside consumers need the old location.
- Whether Google Cloud Workload Identity Federation is in use, and the Google Cloud project.

If a value is unknown, record it as a decision in the plan and continue.

## PLAN mode

1. Check tools (see "Tools"). Report what is missing and how to install it; do not install anything.
2. Run the inventory on the local checkout (read-only):

   ```sh
   python3 ${CLAUDE_SKILL_DIR}/scripts/inventory_github_repo.py PATH_TO_CHECKOUT \
     --json-out SCRATCH_DIR/inventory.json
   ```

   `SCRATCH_DIR` is a temporary folder outside the repository. The command prints a markdown report
   and writes the JSON beside it (`--format json` prints only the JSON). The script lists workflow triggers,
   jobs, actions, runner labels, secret and variable NAMES, environments, OIDC use, CODEOWNERS,
   Dependabot, other `.github/` files, submodules, LFS and hard-coded GitHub URLs. It says
   "could not parse" for YAML it cannot read; read those files by hand.
3. Fetch the current importer page and the Actions migration page. Compare with
   references/importer.md and references/actions-to-gitlab-ci.md. Note any difference.
4. Render the checklist:

   ```sh
   python3 ${CLAUDE_SKILL_DIR}/scripts/render_cutover_checklist.py SCRATCH_DIR/inventory.json \
     --gitlab-host HOST --gitlab-path GROUP/PROJECT --tier free|premium|ultimate|unknown
   ```

5. Write the plan with these sections, in this order:
   - **Summary**: source, target, tier, what is found, the biggest risks.
   - **What the importer carries and drops**, for this repository (references/importer.md).
   - **Pipelines**: one line per workflow with its GitLab translation and open questions
     (references/actions-to-gitlab-ci.md). The target pipeline is built on the hardened reference
     in the `ci-harden` skill; image signing is covered by `image-supply-chain`.
   - **Secrets and variables**: names, proposed masking and protection, who enters each value.
   - **Google Cloud trust**: the provider and binding drafts and the test plan
     (references/gcp-wif-trust.md), only when the inventory shows OIDC use.
   - **Repository rules**: branch protection, approvals, push rules, CODEOWNERS, Dependabot to
     Renovate, webhooks, Slack (references/repo-settings.md). Slack work beyond this belongs to the
     `team-comms` plugin.
   - **Mirror, URLs, cutover, rollback, archive** (references/cutover-and-rollback.md).
   - **Gaps and decisions for the user**: tier gaps, unparsed files, manual translations, security
     owner question, items the checkout cannot show.
   - **The cutover checklist**, as rendered.
6. Offer to save the plan and checklist where the user wants them. Offer EXECUTE mode. Stop.

PLAN mode runs the bundled scripts and read-only `gh`, `glab`, `git` and `gcloud` commands. It makes no
write calls.

## EXECUTE mode

Start only when the user says to execute (the `execute` argument counts). Confirm the plan was
accepted and the decisions are filled in. Then follow references/execute-commands.md: the step
protocol, the secrets protocol and the step catalogue.

Order of steps:

1. Preflight reads (auth status, instance version, repository ID).
2. Create the target group if missing. The import creates the project.
3. Run the import (user runs it in their own terminal). Verify with the status read.
4. Verify the import against the checklist; list gaps.
5. Create non-secret variables; then secret variables, names listed, values entered by the user.
6. Protected branches and merge settings.
7. Google Cloud trust: provider, then binding (gcloud drafts).
8. Commit the translated `.gitlab-ci.yml` on a branch and open a merge request.
9. Webhooks, Slack app, runners.
10. Mirror, then remotes.
11. Cutover, then (after the rollback window and a second confirmation) archive the GitHub repository.

After each write, run its read check and show the result before offering the next step.

## Which reference to read

| Need | File |
|---|---|
| What the importer moves, API and UI methods, user mapping | references/importer.md |
| Translate workflows and expressions | references/actions-to-gitlab-ci.md |
| Workload Identity Federation for GitLab, and removing GitHub | references/gcp-wif-trust.md |
| Branch rules, approvals, CODEOWNERS, Renovate, webhooks, Slack, tiers | references/repo-settings.md |
| Mirror, URL changes, remotes, cutover, rollback, archive | references/cutover-and-rollback.md |
| Exact drafted commands and the step protocol | references/execute-commands.md |
| Source URLs, fetch dates, what was and was not verified | references/sources.md |
| Starting point for dependency updates | ../ci-harden/templates/renovate.json |

Read only the files the current step needs.

## Tools

List these in the plan and check each with the command shown. Free and open-source tools come first.

| Tool | Check | Used for |
|---|---|---|
| python3 3.11 or later | `python3 --version` | the bundled scripts (standard library only) |
| git | `git --version` | clones, remotes |
| gh | `gh --version`, `gh auth status` | read GitHub settings; archive (with confirmation) |
| glab | `glab --version`, `glab auth status` | GitLab API calls, variables, merge requests |
| gcloud | `gcloud --version` | Workload Identity Federation (only when in use) |
| gitleaks | `gitleaks version` | scan full history for committed secrets before it moves |
| osv-scanner, trivy | `osv-scanner --version`, `trivy --version` | free replacements for Dependabot alerts |
| jq | `jq --version` | the token exchange in the deploy job |

## Behaviour checks

Claude may start this skill from chat, so the evals in `evals/gitlab-migration-*` check the
`Skill` call and what the session does: a plan request loads the skill and produces a plan and
no write calls, a request to run the import or paste a token produces a draft and a request for
a go, and unrelated CI questions do not load the skill or produce a migration plan.

## Done when

- PLAN: the user has the inventory, the plan with gaps and decisions, and the checklist.
- EXECUTE: every step the user approved ran and its read check passed, and the rest are listed as
  not run.
