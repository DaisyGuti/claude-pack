# tickets

A ticket flow for Claude Code on GitHub or GitLab: write a ticket that workers can build,
plan it, groom the board, and have ticket workers take Ready tickets to an open pull or merge
request in parallel, each on the Claude model its label calls for.

| Command | What it does |
| --- | --- |
| `/tickets:write-ticket` | Files a bug or idea as a ticket in the shape workers need, after checking it is not already built, superseded or ticketed. Sets priority, model, run label and lane |
| `/tickets:plan-ticket` | Posts a plan of about 200 words on one ticket and sets its model and run labels |
| `/tickets:daily-grooming` | Tidies the whole board: settles finished work to Done, flags duplicates, syncs priorities, promotes to Ready, plans what is unplanned |
| `/tickets:work-tickets` | Works your Ready tickets in parallel waves with `tickets:ticket-worker` agents |
| `/tickets:ticket-worker` | Works one named issue from plan to an open review |

Every command changes the tracker or opens a review, so none of them runs unless you type it.

## What you need

- A current Claude Code. Version 2.1.292 or later is needed to pass a ticket's `effort:` label
  to a worker.
- `git`, Python 3.11 or later, and the CLI for your tracker, signed in: `gh` (with the `repo`
  and `project` scopes) for GitHub, or `glab` and `jq` for GitLab.
- A local clone of each repo whose tickets you work.

## First run

The first command you run creates your team's registry at
`${CLAUDE_PLUGIN_DATA}/registry.md` (under `~/.claude/plugins/data/`, so a plugin update never
overwrites it) and stops. Open it and fill in:

- **Tracker** and **Host**: `github` or `gitlab`.
- **Board**: your GitHub Project (owner and number) or GitLab board (scope, path, board).
- **Lanes** and **Priority**: the exact Status options and Priority options on the GitHub
  board, or the labels that stand for them on GitLab.
- **Labels** and **Model labels**: the blocked and run labels, and the label per model tier.
- **Repos**: each repo's remote, local clone and product brief.

Run any command again; it checks the registry and names whatever is still missing.

## How a ticket moves

1. `write-ticket` files it in the backlog (or Ready) with a priority, a run label and a model
   label.
2. `plan-ticket` or `daily-grooming` posts the plan and moves it to Ready.
3. `work-tickets` (or `ticket-worker` for one issue) starts a worker on the model the label
   names. The worker moves the card to In progress, builds on its own branch in its own
   worktree, runs the repo's tests, opens a pull or merge request that closes the issue when
   merged, and moves the card to In review.
4. A person reviews and merges. Merging closes the issue; the next `daily-grooming` pass moves
   the card to Done and frees any ticket that waited on it.

Work that cannot proceed is held with the `blocked` label and a `Blocked: dependency`,
`decision`, `live action` or `failure` comment that says what clears it. Workers never push to
the default branch, never merge, and never close an issue.

## Model per ticket

The model label maps to a Claude tier: `fast` runs on Haiku, `workhorse` on Sonnet and
`frontier` on Opus. `work-tickets` passes the model when it starts each worker. An
`effort:<level>` label on a ticket sets the worker's reasoning effort.

## Companions

The official `code-review` and `pr-review-toolkit` plugins review the diff a worker opens. The
official `github` and `gitlab` plugins add MCP access to the hosts and are optional here.
`references/platform-notes.md` lists the Claude Code behavior this plugin relies on and a
starting list of commands worth allowing.
