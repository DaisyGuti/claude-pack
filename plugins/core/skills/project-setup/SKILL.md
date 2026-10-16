---
name: project-setup
description: Writes or refreshes a repository's CLAUDE.md for this team, built from the repo's real files - its build, test and lint commands, the branch-then-pull-request-or-merge-request rule, security rules for a government product (no secrets or customer data in code or prompts, pinned dependencies, signed commits where the repo uses them), and pointers to the pack's security and build plugins. Use for "set up Claude for this repo", "onboard this repo", "create or update CLAUDE.md", "add our team rules to this project", or when starting work in a repo that has no CLAUDE.md, even if the user never says CLAUDE.md. To score or audit an existing file, use the official claude-md-management plugin.
argument-hint: "[path to the repo, default: current directory]"
---

# Project setup

Give a repository a `CLAUDE.md` that tells Claude what it cannot infer from the code: the
real commands, what done means, how work lands, and the team's security rules. Every fact
comes from a file in the repo. Ask a question only after the draft exists, and only where a
step below says the choice is the user's.

## Boundaries

- Read anything in the repo. Write only the repo's `CLAUDE.md` (at the repo root, or
  `.claude/CLAUDE.md` if that is where the repo already keeps it).
- Do not commit, push or open a review. Show the diff and let the user land it through the
  repo's normal pull or merge request flow.
- If the path is not inside a git repository, ask for the repo path and stop.
- Rewording an existing prompt or agent file is a different job. Scoring or auditing an
  existing CLAUDE.md is the official `claude-md-management` plugin's job; this skill writes
  the first file with the team's rules in it, and refreshes one that is stale.

## Steps

1. **Scan.** Run `python3 ${CLAUDE_SKILL_DIR}/scripts/scan_repo.py $ARGUMENTS` (execute it; do
   not read it; with no argument it scans the current directory). It prints JSON: host (GitHub or GitLab), default branch, the instruction
   files present, package scripts, Makefile targets, CI definitions with their `run:` and
   `script:` commands, lockfiles, Dockerfile base images and whether each is pinned by digest,
   GitHub Actions pinned or not, and how many of the last commits are signed or follow
   Conventional Commits. It needs Python 3.11 or later and `git`; check with
   `python3 --version`.
2. **Read what exists.** Any `CLAUDE.md` and `AGENTS.md` from the repo root down to the working
   directory, `CONTRIBUTING.md`, the README, the CI files the scan lists, and the pull or merge
   request template. A `CLAUDE.md` that is empty or holds only placeholders counts as absent.
3. **Fill the template** at [assets/CLAUDE.template.md](assets/CLAUDE.template.md).
   - **Commands.** Take each from a manifest script, a Makefile target or a CI step the scan
     lists, and name the source in parentheses. A command the repo does not state is written
     `UNKNOWN`; never guess one.
   - **Landing changes.** The first line is always: branch, push the branch, open a pull
     request (GitHub) or merge request (GitLab) into the default branch, never commit to it.
     Use the host the scan reports. Add the repo's own review rules after it, each from a file
     that states it: code owners, the template to fill, title or label conventions, what must
     pass before a merge. Never write "commit straight to main", whatever the history shows.
   - **Commit style.** Name Conventional Commits only when most sampled commits follow it or a
     file says so.
   - **Signed commits.** Keep the signed-commits line only when `gpgsign_config` is `true` or
     most sampled commits carry a signature. Otherwise delete it. This skill never turns
     signing on.
   - **Security rules.** Keep the section as written. Fill `{{secret mechanism}}`,
     `{{.env.example}}` and `{{lockfile}}` from the scan; delete the clause when the repo has
     none. Add a repo-specific rule only when a repo file states it. When the scan shows
     unpinned base images or unpinned Actions, add one line under Dependencies naming them as
     a known gap for a person to fix; do not rewrite the Dockerfile or workflow here.
   - **Pointers.** Keep the lines naming the `guardrails`, `security` and `secure-build`
     plugins. Tell the user in the report which of them are not installed (`/plugin` lists
     what is).
   - **Existing rules files.** Link to them and copy nothing. When an `AGENTS.md` exists, the
     CLAUDE.md imports it with a line `@AGENTS.md` and adds only what Claude Code needs.
   - Include only facts that change how an agent works in this repo. Leave out history,
     progress notes and anything the code makes obvious. Delete every line the repo gives no
     support for.
   - Remove the template comment and every `{{placeholder}}`.
4. **Check it.** Run `python3 ${CLAUDE_SKILL_DIR}/scripts/check_claude_md.py <path to the new
   CLAUDE.md>` (execute it). It fails on leftover placeholders, over 200 lines, a missing
   Commands, Landing or Security section, a secret-shaped string, a machine-specific path, a
   `make` target or package script that does not exist, and a link or `@import` to a missing
   file. Fix each failure and rerun until it exits 0. Then confirm every `UNKNOWN` it counts
   is reported to the user.
5. **Audit for conflicts.** Compare the draft against the other instruction files Claude Code
   will load (`~/.claude/CLAUDE.md` is the user's own; parent-directory and subdirectory
   CLAUDE.md files). Fix a conflict by changing the draft so the file that owns the fact stays
   its only copy; leave every other file unchanged. A rule anywhere that says to commit or push
   to the default branch goes in the report as a conflict with the review-only rule: the draft
   keeps the review-only line, and the file holding the old rule stays as it is for the user to
   change.
6. **Show it.** Print `git diff` for the file (or the new file) and stop. Landing is the
   user's call.

When a `CLAUDE.md` already exists, refresh it in place: keep rules that are still true,
correct stale commands and paths, and say in the report what you removed and why.

## Report

The file path; a few lines on what it now tells Claude; every `UNKNOWN` left for the user to
fill; any conflict you resolved or left, including any existing rule that says to commit to the
default branch; the team plugins that are not installed; the known gaps from the scan (unpinned
images or actions). Background on each rule and its source is in
[references/rules-and-sources.md](references/rules-and-sources.md).
