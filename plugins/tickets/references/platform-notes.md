# Claude Code facts the ticket skills rely on

Each fact names its source, read 2026-10-16. When a fact changes, this file is the one place
to correct; the skills and the worker agent point here instead of restating it.

## Contents

- Plugin paths and the registry
- Worktrees for workers
- Model and effort at spawn
- Permission prompts
- Related plugins

## Plugin paths and the registry

- `${CLAUDE_PLUGIN_ROOT}` is the plugin's install folder, which changes on every update.
  `${CLAUDE_PLUGIN_DATA}` is its persistent folder (under `~/.claude/plugins/data/`), which
  survives updates. Claude Code substitutes both in a plugin skill's `SKILL.md` text and in
  Bash rules in its `allowed-tools`. It does not substitute them in files the skill links to,
  in the agent file, or in the environment of Bash commands. So each `SKILL.md` prints the two
  absolute paths once, and every reference file and the worker agent receive those paths from
  it. Source: https://code.claude.com/docs/en/skills ("String substitutions").
- The team's registry therefore lives at `${CLAUDE_PLUGIN_DATA}/registry.md`, created from
  `registry.example.md` by `scripts/registry.py ensure` on the first run. Run records and extra
  worktrees live beside it, under `state/` and `worktrees/`.

## Worktrees for workers

- A subagent with `isolation: worktree` runs in a temporary git worktree of the repository the
  session was launched from, branched from that repo's default branch on the remote. It is
  removed automatically when the subagent finishes without changes; one with changes stays until
  Claude Code's periodic sweep can remove it without losing work (pushed work counts as safe).
  Source: https://code.claude.com/docs/en/worktrees ("Isolate subagents with worktrees").
- That isolation covers only the launch repo. A ticket in another repo of the registry gets a
  worktree the worker makes with `git worktree add` from the registry's clone, under
  `${CLAUDE_PLUGIN_DATA}/worktrees/`. Edits outside the session's folders can prompt for
  approval once.
- A subagent in a default-location worktree does not load that repo's `CLAUDE.md` at its root,
  so the worker reads `CLAUDE.md`, `AGENTS.md` and `CONTRIBUTING.md` itself (same page).
- Commands that redirect git into the launch repo's main checkout (`git -C`, `GIT_DIR`, a `cd`
  into it) are refused while a worker runs in its worktree. The worker therefore never touches
  the launch repo's primary clone (same page, "How Claude Code enforces isolation").

## Model and effort at spawn

- The Agent call's `model` parameter beats the agent file's `model`, which beats the session's.
  Aliases `haiku`, `sonnet` and `opus` resolve to the newest model of that family. An
  organization's allowlist can substitute another model. Source:
  https://code.claude.com/docs/en/sub-agents ("Choose a model").
- A per-invocation `effort` parameter exists from Claude Code v2.1.292; the agent file's
  `effort` field applies otherwise. Source: same page ("Choose an effort level").
- Claude Code refuses a spawn beyond 20 running subagents by default
  (`CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`). Source: same page ("Concurrent subagent limit").

## Permission prompts

Workers run `git`, the tracker CLI and the repo's own test command. A foreground worker asks
in the user's session for anything not already allowed; a background worker surfaces the same
prompts there (sub-agents page, "Run subagents in foreground or background"). To cut the noise,
allow the read-only commands the skills use in the user's `.claude/settings.local.json`, for
example:

```json
{
  "permissions": {
    "allow": [
      "Bash(git fetch *)", "Bash(git status *)", "Bash(git log *)", "Bash(git worktree *)",
      "Bash(gh issue view *)", "Bash(gh issue list *)", "Bash(gh label list *)",
      "Bash(gh pr list *)", "Bash(gh auth status*)", "Bash(glab auth status*)"
    ]
  }
}
```

Writes to the tracker (`gh issue edit`, `gh pr create`, `glab api` with `PUT` or `POST`) are the
steps a person may want to see, so this plugin does not pre-approve them. A team that trusts
the flow can add them.

## Related plugins

- The official `github` and `gitlab` plugins add MCP servers for repository and issue access.
  This plugin needs only the `gh` or `glab` command line signed in, so it works without them.
- After a worker opens a review, the official `code-review` and `pr-review-toolkit` plugins
  review the diff before a person merges.
