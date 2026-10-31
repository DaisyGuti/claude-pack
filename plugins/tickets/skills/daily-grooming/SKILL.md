---
name: daily-grooming
description: Tidies the whole ticket board so that Ready means safe to dispatch. Settles closed and merged work to Done, flags duplicates, syncs priorities, promotes tickets to Ready, and plans and labels each Ready ticket (plan, priority, model, run), for every person's tickets on a GitHub Project or GitLab board. Use for "groom the board", "clean up my backlog", "get Ready in shape", "settle the finished tickets", even when the user names no lane or label. Try --dry-run first.
argument-hint: "[--dry-run] [--project N --owner OWNER] [--repo NAME] [--context FILE]"
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/scripts/registry.py *) Bash(${CLAUDE_PLUGIN_ROOT}/scripts/resolve_model.py *)
---

# Daily grooming

Keeps a GitHub Project board or GitLab issue board honest so that "Ready" means "safe to
dispatch": a plan, a priority, a model label and a run label on every ready ticket. It covers
the whole board, every person's tickets.

The request: $ARGUMENTS

```text
/tickets:daily-grooming                            # the whole default board, every repo in the registry
/tickets:daily-grooming --dry-run                  # print every change and plan, change nothing
/tickets:daily-grooming --project 2 --owner my-group   # a different board (a pasted board URL works too)
/tickets:daily-grooming --repo my-app              # only these registry repos; repeatable
/tickets:daily-grooming --context FILE             # one brief for the whole run; repeatable
```

Never ask for a project number or a repo list. `--context FILE` is right only for a
single-product board: otherwise each ticket is judged against its own repo's brief.

Paths used below (read them as `<scripts>` and `<data>`):

- Scripts: `${CLAUDE_PLUGIN_ROOT}/scripts`
- Data (the team's registry): `${CLAUDE_PLUGIN_DATA}`

## Before the pass

1. Run `<scripts>/registry.py ensure --data-dir <data>`. Exit 3 means it just created the
   team's registry and exit 4 means it is unfilled: follow
   [registry-rules.md](${CLAUDE_PLUGIN_ROOT}/references/registry-rules.md) ("Where the registry
   lives"), show what it printed and stop. The same file says how a pasted board URL resolves.
2. Read the one tracker adapter for the registry's tracker, in full, once:
   [github.md](${CLAUDE_PLUGIN_ROOT}/references/trackers/github.md) or
   [gitlab.md](${CLAUDE_PLUGIN_ROOT}/references/trackers/gitlab.md). Every tracker action is a
   named operation shown in bold in the procedure.
3. Read [grooming.md](${CLAUDE_SKILL_DIR}/references/grooming.md) in full. It holds the steps,
   in order: set up and capture the board; fetch the items and settle closed or merged work to
   done before anything else looks at it; flag duplicates; audit each open ticket, with the
   priority sync; triage lanes and order the Ready lane; apply the changes; make every Ready
   ticket dispatchable; print the summary.
4. Planning follows
   [plan-one-ticket.md](${CLAUDE_PLUGIN_ROOT}/references/plan-one-ticket.md), the same
   procedure `/tickets:plan-ticket` uses. Plan each ticket in its own subagent started with
   `model: opus`, in parallel when there are several, so planning runs on Opus whatever the
   session's model ([model-selection.md](${CLAUDE_PLUGIN_ROOT}/references/model-selection.md),
   "Planning runs on frontier"). Priority, run, model and blocked labels mean what
   [ticket-labels.md](${CLAUDE_PLUGIN_ROOT}/references/ticket-labels.md) says.

## The standing rules

- **Settle closed work first.** A closed issue or merged review goes to done and is never
  audited, prioritised, triaged or planned.
- **Never touch a ticket a worker or a person put somewhere.** A ticket in progress, in the
  blocked lane, carrying the blocked label, or with an open linked review keeps its lane and is
  never planned. Grooming only flags the ones that look wrong: a blocked label with no
  `Blocked:` comment, and a ticket in the blocked lane without the label.
- **Never change an assignee.** A Ready ticket with no assignee is listed under Needs
  Attention, because `/tickets:work-tickets` works only tickets assigned to its person.
- **Preserve labels.** Remove only a priority label being replaced; add rather than remove when
  unsure.
- **No check-ins.** Finish the pass, then report. Failed writes go in the summary, and the pass
  continues. Before the summary, confirm each step ran or was skipped for a reason you can
  state, and that every Ready ticket is planned, labelled or listed under Needs Attention. The
  summary opens with what changed on the board.
- **`--dry-run` runs read operations only.** It prints every planned change and every ticket it
  would plan, and writes nothing, creates no label and spawns nothing.
- **Ready means planned.** A ticket goes to the ready lane only with a `### Final Plan` and no
  open blocker, and a planned, unblocked ticket goes there in the same pass, never left in the
  backlog.
- **Duplicates and lane order are reported.** Duplicates are listed for a person and never
  closed or merged. The Ready order goes in the summary, in waves of tickets that share no
  file, for someone to apply, since no tracker operation reorders a lane.
