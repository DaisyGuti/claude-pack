---
name: ticket-worker
description: >-
  Works one specific GitHub or GitLab issue from plan to an open pull or merge request, in its
  own git worktree, on the Claude model its ticket label calls for, and moves the board card.
  Merging the review closes the issue. Use for "work issue 42 in my-app", "build ticket 42",
  "take #42 to a PR", even when the user names no repo. For the whole Ready queue use
  work-tickets.
argument-hint: "<issue number> [--repo NAME] [--model haiku|sonnet|opus]"
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/scripts/registry.py *) Bash(${CLAUDE_PLUGIN_ROOT}/scripts/resolve_model.py *)
---

# Ticket worker

Takes one issue assigned to the signed-in user from plan to an open review, by handing it to
the `tickets:ticket-worker` agent. The agent works in its own git worktree, follows the plan
and the repo's own rules, and never touches the default branch. A skill cannot choose the
session's model, so this skill reads the ticket's model label and starts the agent on that
model.

The request: $ARGUMENTS

```text
/tickets:ticket-worker 42                       # the repo is inferred from the current folder
/tickets:ticket-worker 42 --repo my-app
/tickets:ticket-worker 42 --repo my-app --model opus   # a model you name outranks the label
```

Paths used below (read them as `<scripts>` and `<data>`):

- Scripts: `${CLAUDE_PLUGIN_ROOT}/scripts`
- Data (the team's registry, extra worktrees): `${CLAUDE_PLUGIN_DATA}`

## 1. Set up

1. Run `<scripts>/registry.py ensure --data-dir <data>`. Exit 3 means it just created the
   team's registry and exit 4 means it is unfilled: follow
   [registry-rules.md](${CLAUDE_PLUGIN_ROOT}/references/registry-rules.md) ("Where the registry
   lives"), show what it printed and stop. Then `registry.py show --data-dir <data>` gives the
   tracker, board, lanes, priorities, labels, model labels and repos.
2. Read the one tracker adapter for the registry's tracker, in full:
   [github.md](${CLAUDE_PLUGIN_ROOT}/references/trackers/github.md) or
   [gitlab.md](${CLAUDE_PLUGIN_ROOT}/references/trackers/gitlab.md). Every tracker action below
   is a named operation shown in bold.
3. Read [model-selection.md](${CLAUDE_PLUGIN_ROOT}/references/model-selection.md) and the
   worker's contract, [ticket-worker.md](${CLAUDE_PLUGIN_ROOT}/agents/ticket-worker.md), whose
   section 1 is the dispatch message you send. Claude Code behavior it leans on is in
   [platform-notes.md](${CLAUDE_PLUGIN_ROOT}/references/platform-notes.md).

## 2. Find the ticket and check it is the user's

1. **Repo.** `--repo`, else the registry repo whose local clone contains the current folder.
   When neither settles it, ask which repo and stop. The issue number is the one in the
   request. The worker gets a throwaway worktree of the repo Claude Code was started in, so a
   current folder outside any git repository stops here: tell the user to start Claude Code
   inside one of the registry's clones.
2. Run **auth-check**, **current-user**, **capture-board**, then **list-items** and match the
   item on `(number, repo)`; keep its `item_ref`. An issue that is not on the board skips every
   board move: say so in the report.
3. **read-issue**. If it is assigned to someone else, or to nobody, stop before anything else:
   change nothing on the ticket, say who it is assigned to (or that it is unassigned), and offer
   to assign it to the current user with **assign**. Run **assign** only when the user says to.
   A closed issue or one carrying the blocked label also stops here, with that fact.

## 3. Choose the model

1. A model the user named (`--model`, or "use opus") outranks the label.
2. Otherwise run `<scripts>/resolve_model.py --registry <data>/registry.md <every label on the
   issue>` and use the `model` and `effort` it prints (see model-selection.md for passing the
   effort).
3. No model label, several, or a label that maps to no tier (resolver exit 3, 4 or 5): use
   `sonnet` and say in the report which of those it was. Do not guess a tier.

## 4. Hand it to the worker

Build the dispatch message exactly as section 1 of the agent file describes, with `mode`
`direct`, `slot_id` `solo`, `ticket_number`, `ticket_repo` and `repos` (the repo, plus any
other repo the issue body names that the registry lists), `item_ref`, `assignee` (the
current user), `project` (from the registry and **capture-board**), `repo_map`,
`worktree_root` `<data>/worktrees/solo`, `files.adapter` and `files.labels` as absolute paths,
`model`, `validate_plan_first` `true`, and `context_files` (the repo's product brief).

Make one Agent call: `subagent_type` `tickets:ticket-worker`, `model` set to the chosen model,
`effort` set to the resolved effort when it is not null (Claude Code v2.1.292 or later; on an
older version leave it out and say so), `run_in_background: false`, and the dispatch message as
the prompt. The agent file sets `isolation: worktree`. Wait for it. If the spawn fails because
the agent type is unavailable, tell the user to check that the `tickets` plugin is enabled; do
not retry in a loop and do not do the worker's job in this session.

## 5. Report

Relay the worker's report as yours. Put one line before it saying which model ran and why
(the label, the user's choice, or the fallback). The worker's last line is a `RESULT` line;
read it for the status and the review links, and keep it out of your own summary. A ticket in
review is not closed: say that merging the review closes it.
