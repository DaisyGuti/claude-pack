---
name: work-tickets
description: Works the user's Ready tickets from a GitHub Project or GitLab board in parallel waves. Starts one ticket-worker agent per ticket, each on the Claude model its ticket label calls for (Haiku, Sonnet or Opus), each in its own git worktree, and ends with a pull or merge request open per ticket. Use for "work my ready tickets", "run my queue", "work the P1s", or a pasted board URL, even when the user names no lane. For one issue use ticket-worker.
argument-hint: "[--dry-run] [--priority P1] [--max-parallel N] [--limit N] [--repo NAME] [--project N --owner OWNER] [--clear-skipped]"
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/scripts/registry.py *) Bash(${CLAUDE_PLUGIN_ROOT}/scripts/resolve_model.py *) Bash(${CLAUDE_PLUGIN_ROOT}/scripts/ticket_state.py *)
---

# Work tickets

Read [orchestrator.md](${CLAUDE_SKILL_DIR}/references/orchestrator.md) in full before you
start. It holds the whole procedure: flags and defaults, the Ready gate, label rules, model
resolution, the run record, wave dispatch and reaping, and the report.

The request: $ARGUMENTS

Paths used below and in the procedure (read them as `<scripts>` and `<data>`):

- Scripts: `${CLAUDE_PLUGIN_ROOT}/scripts`
- Data (the team's registry, run records, extra worktrees): `${CLAUDE_PLUGIN_DATA}`

## Before Phase 1

1. Run `<scripts>/registry.py ensure --data-dir <data>`. Exit 3 means it just created the
   team's registry and exit 4 means it is unfilled: follow
   [registry-rules.md](${CLAUDE_PLUGIN_ROOT}/references/registry-rules.md) ("Where the registry
   lives"), show what it printed and stop. Never ask the user for a project number or a repo
   list: they come from the registry.
2. Read the one tracker adapter for the registry's tracker, in full:
   [github.md](${CLAUDE_PLUGIN_ROOT}/references/trackers/github.md) or
   [gitlab.md](${CLAUDE_PLUGIN_ROOT}/references/trackers/gitlab.md).
3. Read [ticket-labels.md](${CLAUDE_PLUGIN_ROOT}/references/ticket-labels.md) (the labels and
   the Blocked comment),
   [model-selection.md](${CLAUDE_PLUGIN_ROOT}/references/model-selection.md) (how a model label
   becomes a spawn) and the worker's contract,
   [ticket-worker.md](${CLAUDE_PLUGIN_ROOT}/agents/ticket-worker.md), whose section 1 is the
   dispatch message you send. Claude Code behavior the procedure leans on (worktrees, spawn
   parameters, permission prompts) is in
   [platform-notes.md](${CLAUDE_PLUGIN_ROOT}/references/platform-notes.md).

`/tickets:work-tickets` with no arguments works the whole default board;
`/tickets:work-tickets --priority P1` narrows to one priority.

## The standing rules

- Only Ready tickets assigned to whoever is signed in to the tracker CLI are worked.
  Unassigned tickets and tickets assigned to others are counted in the report and never
  touched. There is no flag for someone else's tickets; that takes signing in as them.
- A Ready ticket carrying the registry's blocked label is held: never dispatched, never
  touched, and listed in the dry run and the report with the kind from its latest `Blocked:`
  comment.
- Work the whole queue without checking in between waves, stopping only for the procedure's
  halt conditions.
- You orchestrate and the workers implement. Never edit a ticket's code yourself, and keep
  worker output out of the main thread: the run record holds the detail and each worker
  returns one paragraph and a `RESULT` line.
- Every spawn names its model, resolved from the ticket's label with
  `<scripts>/resolve_model.py`. Waves are capped at `--max-parallel` (3 by default).
- Every worker lands its change by pull or merge request, whatever the repo's own rules say,
  and ends `review_opened`. That is finished work: record it with its review link, count it as
  "in review", and never treat it as blocked. Merging the review closes the issue and
  `/tickets:daily-grooming` settles it to done; no worker closes an issue or moves a card to
  done.
- A worker moves its card to In progress when it starts and to the review lane when its review
  opens (if the board has one).
- Finish the queue, then report with the counts first: how many tickets are in review, blocked
  and not dispatched, and what needs the user.
- `--dry-run` has no side effects beyond capturing the board's fields. It prints each ticket's
  tier, resolved model and effort, the counts of Ready tickets left alone, and an "In review"
  line with the link for each earlier run's review that is still open.
