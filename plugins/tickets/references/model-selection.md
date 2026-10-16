# Choosing a model and effort for ticket work

Shared by every skill and agent in this plugin. Sources, read 2026-10-16: Claude Code docs
on [subagents](https://code.claude.com/docs/en/sub-agents) ("Choose a model" and "Choose an
effort level") and [model configuration](https://code.claude.com/docs/en/model-config)
("Adjust effort level").

## The rule

Size each unit of work by the hardest judgment it contains. A long job made of easy calls
stays on a cheap tier. Start at the cheapest tier that should clear the quality bar, and
when one unit comes back weak, rerun that unit one tier up. A model the user names outranks
this guide.

## From ticket label to model

A ticket carries one model label. The registry's Model labels table maps each label to a
tier (`fast`, `workhorse`, `frontier`), and each tier runs on a Claude model alias:

| Tier | Alias | Typical work |
| --- | --- | --- |
| fast | `haiku` | Mechanical work with a crisp rubric: a rename, a config bump, a copy tweak, wiring an existing check into an existing pipeline |
| workhorse | `sonnet` | Spec-driven implementation inside an existing seam, most bug fixes, test additions. The default when in doubt |
| frontier | `opus` | A wrong call is expensive to unwind: new architecture, open tradeoffs, subtle correctness or performance work |

Run the resolver so the mapping lives in one place. `<scripts>` and `<data>` are the two
paths printed at the top of the skill that sent you here:

```bash
<scripts>/resolve_model.py --registry <data>/registry.md <label> [<label> ...]
```

Pass every label on the ticket. It prints `{"tier", "model", "effort", "label"}`. The
aliases always point at the newest model of that family, so nothing here carries a model
version. Exit 3 means the ticket has no model label, 4 means labels for different tiers
conflict, 5 means a `model:` label maps to no tier.

## Passing the model and effort at spawn

When a skill starts a `tickets:ticket-worker`, the Agent call sets `model` to the printed
`model`. The agent file's own `model: sonnet` applies only when a spawn names none, and the
spawn's value wins over it.

`effort` is set only when the ticket carries an `effort:<level>` label (`low`, `medium`,
`high`, `xhigh` or `max`). Without one, the agent file's `effort: medium` applies. The
per-invocation `effort`
parameter needs Claude Code v2.1.292 or later; on an older version leave it out and say in
the report that the label could not be honored. A level the chosen model does not support
runs at the highest level it does support.

An organization may restrict which models are available. Claude Code then substitutes the
newest permitted model of the same family and tells the user, so the report names the model
a worker actually ran on (`/tasks` shows it) when it differs from the resolver's.

## Escalating

Name which axis a weak result needs:

- **More depth on the same model.** The worker redid an analysis and only trusted a later
  pass, held more call sites than it could track, or knew of an edge case it did not chase.
  Raise the effort one step.
- **A different kind of call.** The ticket turned out to hold a frontier judgment. Move up a
  tier.

A worker that ran on the wrong tier posts a model-fit note after its review opens
(ticket-worker protocol, section 9). The next person who assigns the label reads it.

## Delegating

- Parallelize read-heavy units freely. Run write-heavy units in parallel only when each has
  its own git worktree, which every ticket worker does.
- Each spawn message states the unit, its inputs, what to return and what done means, since
  a subagent starts without the conversation.
- A worker returns the outcome first and keeps findings, error text and numbers intact. It
  quotes errors and exit codes as printed.
- When one unit builds and another validates, keep them separate. Only the validator's
  result counts as validation.
