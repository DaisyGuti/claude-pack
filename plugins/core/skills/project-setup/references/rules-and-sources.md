# Why each rule is in the template, and where it comes from

Read this when a repo pushes back on a rule or asks where it came from. Sources were read on
2026-10-16; fetch the page again before quoting a number or a flag.

## Contents

- How Claude Code treats a CLAUDE.md
- The Security rules section, rule by rule
- How a rule becomes enforced
- Judgment calls in the skill

## How Claude Code treats a CLAUDE.md

Source: Claude Code memory documentation, <https://code.claude.com/docs/en/memory>.

- A CLAUDE.md is context. Claude Code "treats them as context, not enforced configuration".
  To block an action regardless of what Claude decides, use a `PreToolUse` hook.
- Size: target under 200 lines per file. Longer files use more context and reduce adherence.
  Imports (`@path/to/file`) organize a long file but do not reduce its context cost, because
  imported files load at launch too. Imports nest to a maximum of four hops.
- Locations: `./CLAUDE.md` or `./.claude/CLAUDE.md` for the team, `./CLAUDE.local.md` (gitignored)
  for one person. Files in subdirectories load on demand when Claude works in them.
- Topic-specific or path-specific rules go in `.claude/rules/*.md`; a rule with a `paths`
  field loads only when Claude works with matching files.
- `AGENTS.md`: with no CLAUDE.md, Claude Code reads AGENTS.md. With both, it reads CLAUDE.md
  only, so a CLAUDE.md that should include AGENTS.md says `@AGENTS.md` on its own line.
- `/init` generates a first CLAUDE.md from the code. The official `claude-md-management`
  plugin audits and improves an existing one, and `claude-code-setup` recommends hooks,
  skills and servers. This skill covers the gap: a first file written from the repo's own
  files, with the team's rules already in it, checked before it is committed.

## The Security rules section, rule by rule

| Rule in the template | Why | Source |
| --- | --- | --- |
| No secrets in code, config, tests, fixtures, logs, commits, tickets or prompts | A committed or prompted secret has to be treated as leaked; history keeps it | Team policy for government products |
| No customer, personal or controlled government data in prompts, fixtures or test output | Prompts and fixtures leave the boundary the data was approved for | Team policy for government products |
| Respect the lockfile; pin base images by digest | A tag is mutable; by pinning to a digest "you're guaranteed to always use the same image version, even if a publisher replaces the tag" | Docker build best practices, "Pin base image versions", <https://docs.docker.com/build/building/best-practices/> |
| Pin CI actions to a commit SHA | Pinning to a SHA means a bad actor would need a SHA-1 collision to slip a change into the action | GitHub, Security hardening for GitHub Actions, <https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions> |
| Human review for authentication, authorization, payments, personal data, secrets | A wrong call here is expensive to unwind and is not caught by tests alone | Team policy for government products |
| Signed commits only when the repo already uses them | The scan reports `commit.gpgsign` and how many of the last commits carry a signature; the skill never turns signing on | Repo's own settings |

GitLab has no `uses:` line to pin. The nearest equivalent is pinning `include:` entries and
job images to a fixed ref or digest; the `secure-build` plugin owns that detail.

## How a rule becomes enforced

CLAUDE.md text is advice. A rule that must hold every time belongs in a hook. The team's
hooks live in the `guardrails` plugin (secret leaks, destructive commands). The template
names that plugin so a reader knows which rules are enforced and which are guidance.

## Judgment calls in the skill

- **UNKNOWN over a guess.** A command the repo does not state is written as `UNKNOWN`,
  because a plausible wrong command costs every later session.
- **Lines the scan cannot support are deleted.** A signed-commits line in a repo that does
  not sign commits tells Claude to do something the repo does not ask for.
- **Landing line is fixed.** Branch, then pull or merge request, never the default branch.
  A repo whose files say "commit to main" gets the review-only line anyway, and the conflict
  is listed in the report for a person to settle.
