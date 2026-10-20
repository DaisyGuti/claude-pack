---
name: plan-ticket
description: Plans one ticket before anyone works it, the user's own next ticket or a teammate's. Picks the next Ready ticket (or the numbered one), posts a build plan of about 200 words on it (files to touch, pattern to reuse, how to tell it is done) and sets its model and run labels. Use for "plan my next ticket", "plan ticket 73", "write the plan for the top of my queue", even when the user does not name labels.
argument-hint: "[--all] [--ticket N] [--repo NAME] [--dry-run] [--project N --owner OWNER] [--context FILE]"
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/scripts/registry.py *) Bash(${CLAUDE_PLUGIN_ROOT}/scripts/resolve_model.py *)
---

# Plan ticket

`work-tickets` and `ticket-worker` build from a ticket that carries a plan, a model label and
a run label. This skill produces those for one ticket, right before it ships, so the plan is
fresh: plans written weeks ahead go stale when the brief changes. To prepare a whole board's
Ready lane in one pass, use `/tickets:daily-grooming`.

The request: $ARGUMENTS

```text
/tickets:plan-ticket                       # plan the next Ready ticket assigned to you
/tickets:plan-ticket --all                 # pick from anyone's Ready tickets
/tickets:plan-ticket --ticket 73           # plan this ticket, wherever it is
/tickets:plan-ticket --ticket 73 --repo my-app   # when the number exists in several repos
/tickets:plan-ticket --dry-run             # print the plan and labels, change nothing
/tickets:plan-ticket --project 2 --owner my-group   # a different board (a pasted board URL works too)
/tickets:plan-ticket --context FILE        # use this brief instead of the repo's own (repeatable)
```

Paths used below (read them as `<scripts>` and `<data>`):

- Scripts: `${CLAUDE_PLUGIN_ROOT}/scripts`
- Data (the team's registry): `${CLAUDE_PLUGIN_DATA}`

## 0. Set up

1. Run `<scripts>/registry.py ensure --data-dir <data>`. Exit 3 means it just created the
   team's registry and exit 4 means it is unfilled: follow
   [registry-rules.md](${CLAUDE_PLUGIN_ROOT}/references/registry-rules.md) ("Where the registry
   lives"), show what it printed and stop.
2. Run `<scripts>/registry.py show --data-dir <data>` for the tracker, board, lanes, priorities,
   labels, model labels and repos. `registry-rules.md` ("Resolving a project board argument")
   says how a pasted board URL and `--project` / `--owner` resolve. If a role this skill needs is missing
   (the ready lane, say), stop and name the row to add.
3. Read the one tracker adapter for the registry's tracker, in full, once:
   [github.md](${CLAUDE_PLUGIN_ROOT}/references/trackers/github.md) or
   [gitlab.md](${CLAUDE_PLUGIN_ROOT}/references/trackers/gitlab.md). Every tracker action below
   is a named operation shown in bold; run each as the adapter writes it.
4. Read [plan-one-ticket.md](${CLAUDE_PLUGIN_ROOT}/references/plan-one-ticket.md) and
   [ticket-labels.md](${CLAUDE_PLUGIN_ROOT}/references/ticket-labels.md).

## 1. Pick the ticket

Run **auth-check**, then **current-user**: the person running this is whoever is signed in to
the tracker CLI.

**`--ticket N`:** run **list-items** and take the issue items numbered N. If they span several
repos and `--repo` did not settle it, stop and list them. No match, or a closed issue, or one
carrying the blocked label: say so and stop. A ticket in the in-progress lane is planned
anyway; the report says a worker may already have it.

**Otherwise:** run **list-items** on the ready lane and keep:

1. issues only (reviews and drafts are not planned);
2. those assigned to the signed-in login, compared case-insensitively, unless `--all`;
3. those without the registry's blocked label.

Sort by the Priority table's rank, highest first, unset last, stable. Walk that list: resolve
each ticket's repo per the registry rules (skip one that does not resolve, and name it in the
report), run **read-issue**, and the first ticket with no `### Final Plan` comment is the
pick. The model and run labels are not filters; this skill assigns them.

When nothing is left, say so with the counts that explain it (how many Ready tickets belong to
others or to nobody, when `--all` would have found one), and point to
`/tickets:work-tickets --limit 1` for a ticket that already has a plan and
`/tickets:daily-grooming` for a board that needs tidying. Then stop.

## 2. Plan it

Follow `plan-one-ticket.md` for the picked ticket: load a lean context, write one terse plan,
post it, set the labels (judged per `ticket-labels.md`). It holds the 200-word cap and the list
of what a plan may not contain. Do not add to either. `--dry-run` means read-only operations
only: print the pick, the plan and the labels it would set, and change nothing. Carry the
procedure through to its returned line without stopping to ask; if a fact is missing, plan from
the brief and say what you assumed.

## 3. Report

In plain language, short, outcome first. When a ticket was planned:

> Planned `<repo>#<n>`: <title>. Run `/tickets:work-tickets --limit 1` to ship the top of your queue.

Then add only what applies:

- the model label and the run label set, each with a clause of reasoning, and the model the
  tier runs on from `<scripts>/resolve_model.py --tier <tier>`;
- the ticket is assigned to someone else, or to nobody: `work-tickets` works only Ready tickets
  assigned to its own person, so it will not pick this one up until it is assigned to them;
- the ticket is not in the ready lane (`--ticket`): `work-tickets` works only that lane;
- the run label is run-solo: `work-tickets` never dispatches it, because it needs a person;
- the ticket was held instead of planned, and why, and what unblocks it;
- tickets skipped because their repo did not resolve.
