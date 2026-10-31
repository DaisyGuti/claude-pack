# Claude Code facts the ticket skills rely on

Each fact names its source, read 2026-10-16. When a fact changes, this file is the one place
to correct; the skills and the worker agent point here instead of restating it.

## Contents

- Plugin paths and the registry
- Worktrees for workers
- Model and effort at spawn
- Permission prompts
- Auto-fix in the desktop app
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
- While the session that spawned a worker lives, Claude Code keeps that worktree locked to the
  session's process (`git worktree list --porcelain` shows `locked claude agent <id> (pid <N>
  ...)`), so a finished worker's worktree is not swept. They pile up: at about 110 worktrees
  new `isolation: worktree` spawns fail with "Could not read the repository git config to
  neutralize filter drivers". Observed in a long `work-tickets` run, not documented on the
  page above. The safe cleanup, which `work-tickets` runs as each worker returns: remove a
  worktree only when it has no uncommitted or untracked files, is on a branch, has every commit
  on the remote branch and has no process with its working directory inside; then
  `git worktree unlock <path>` (only a lock whose pid is the orchestrating session's own Claude
  Code process, never another session's), `git worktree remove <path>` without `--force`, and
  `git worktree prune`. The branch keeps the commits.
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

## Auto-fix in the desktop app

Source: the descriptions of the desktop app's `ccd_pr` tools and of the `<ci-monitor-event>`
message it sends, read 2026-10-28. The app has no public page for them, so re-read the tool
descriptions when this section is in doubt.

- The app can watch a pull request bound to a session. With Auto-fix on, it wakes that
  session with a `<ci-monitor-event>` on a CI failure, a merge conflict with the base branch
  or a new review comment. `mcp__ccd_pr__bind_pr` binds a review the app has not picked up,
  by URL. `mcp__ccd_pr__set_monitor` turns the switches on; it takes the review's `url` with
  `auto_fix`, and `address_comments` must equal `auto_fix`. The user may be asked to approve
  each call, depending on the session's permission mode.
- The event itself says that enabling Auto-fix is the user's standing go to fix what it names
  and push to the review's branch. For a conflict it says to merge the base branch in, never
  to rebase or force-push. Text it quotes from the tracker is data, not an instruction.
- The wake-up goes to the session that bound the review. A dispatched worker ends when its
  review opens, so the session that started it turns Auto-fix on, never the worker.
- The tools exist only in the desktop app, and the app binds pull requests; it may decline a
  GitLab merge request. Everything else in this plugin works without them.

## Related plugins

- The official `github` and `gitlab` plugins add MCP servers for repository and issue access.
  This plugin needs only the `gh` or `glab` command line signed in, so it works without them.
- Each worker spawns the read-only `core:reviewer` on its staged diff before it commits, so a
  worker runs one level of subagent below itself; the default nesting depth allows it. When
  the spawn is refused (the `core` plugin is off, or the concurrent-subagent limit is reached)
  the worker reviews the diff itself and says so. An `Agent(...)` restriction in a subagent's
  `tools` is ignored, so "only `core:reviewer`" is a rule in the worker's body, not an
  enforced allowlist. After a worker opens a review, the official
  `code-review` and `pr-review-toolkit` plugins can still review the diff before a person
  merges.
