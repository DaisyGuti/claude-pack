# Ticket labels: what each one means and when it goes on

Shared by `write-ticket`, `plan-ticket`, `daily-grooming`, `work-tickets` and
`ticket-worker`. Label and lane names come from the registry; this file holds the judgment
behind them, so every skill assigns them the same way.

## Contents

- Priority
- Run label
- Model label
- Blocked (the one way work is held)

## Priority

One role from the registry's Priority table, judged by its Meaning column. Priority
measures urgency only and never decides the model.

## Run label

Every ticket carries exactly one of the registry's two run labels.

- **run-worker** (`run:worker` by default): there is code or config a worker can build and
  prove with the repo's own tests, fixtures and mocks, with no shared live state. It keeps
  this label even when its last step is a live action no worker can take (a credential, a
  dashboard setting, real money). The worker builds and tests everything else, opens a
  review, and stops at that step (`needs_manual_action`).
- **run-solo** (`run:solo` by default): there is nothing to build at all. The whole ticket
  is a live step, a decision, or manual QA. Workers never pick it up.

Run mode follows from the acceptance criteria, so it is assigned when the ticket is written
and corrected when it is planned. Both labels on one ticket is a contradiction only a
person can settle: report it and change nothing.

## Model label

The tier follows the hardest judgment in the work. A P0 typo is still `fast`. Write the
label the registry's Model labels table maps the tier to.

- **fast** (Haiku): mechanical, one concern, no design judgment. A rename, a dead-code
  sweep, a copy or label tweak, a regex replacement, a dependency bump.
- **workhorse** (Sonnet): ordinary implementation. A multi-file change, a new module that
  mirrors an existing pattern, a schema or prompt edit, test additions, wiring whose design
  is already specified. The default when in doubt.
- **frontier** (Opus): hard. New architecture, several cross-cutting concerns, tradeoffs
  the ticket leaves open, correctness or performance work that needs deep reasoning.

[model-selection.md](model-selection.md) has the detail and how the label becomes a model.
A model label a person put on the ticket stays as it is.

## Blocked

There is one way to say a ticket or a review is held: the registry's blocked label plus a
comment saying what it is blocked on. No label names a person, and there is no separate
"needs review" or "needs decision" label; the comment carries who and what.

**When it goes on.** Whenever work stops on something the person or agent running it
cannot clear: an open dependency, a decision the ticket does not settle, a live step that
needs access a worker does not have, or a failure the worker could not get past. On an
issue someone has started, the label goes on together with a move to the blocked lane. A
ticket filed with a dependency still open keeps the lane it was filed in. On a review that
must not merge yet, the label goes on the review; merge automation and people both read it
as "do not merge". No skill works or plans a ticket that carries the label.

Waiting on review is an ordinary state. A worker's review (every change lands by pull or
merge request) is open for its reviewer to merge, so it never carries the blocked label and
its issue stays unlabelled.

**The comment.** Post it with the label, every time, in this shape:

```text
**Blocked: <kind>**

<What it is blocked on, in one or two plain sentences.>
<What was tried and what was seen. Omit for a dependency.>

Unblocks when: <the concrete event or action that clears it>.
```

`<kind>` is exactly one of:

- `dependency`: a `Depends on:` issue is still open. Name each one.
- `decision`: a choice the ticket cannot settle. List the options, each with its
  consequence, and recommend one.
- `live action`: a step that needs a credential, a dashboard, a real account or real money.
  Say exactly what to do and where, and link the review holding the code.
- `failure`: a build, test, push or tool failure the worker could not clear. Quote the exact
  error.

When the ticket, the repo's `CLAUDE.md` or the registry names who can clear a kind (an
approver, a team), mention them in the comment. Never guess a person.

**Clearing it.** Only a `dependency` block clears itself: when the last open issue a blocked
ticket depends on closes and that ticket's most recent `Blocked:` comment has the kind
`dependency`, the label comes off with a comment saying so. `daily-grooming` does it on its
next pass after the issue closes, whether a merged review closed it or a person did. A
worker never closes an issue, so it never clears one. A person clears every other kind:
remove the label, move the ticket back to the ready lane (or the backlog lane), and comment
what changed. A blocked label with no `Blocked:` comment is never cleared automatically;
whoever finds one asks on the ticket what it is waiting for.
