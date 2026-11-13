# Batches: one parent, one branch, one review

A **batch** is a parent with a few child tickets that ship together: one worker, one
branch, one pull or merge request, one CI run. It keeps the board from filling with small
tickets that each need a review of their own. A ticket with no parent is a **single** and
is worked alone, exactly as before batching existed.

The registry's Batches section turns it on (`registry.py show` prints `batching`, with
`mode` and `size`). With `mode` `off`, nothing in this file applies: no parent is read,
formed or dispatched.

## Contents

- Where parents live
- What a parent is not
- Forming batches (daily-grooming)
- Joining a batch (write-ticket, plan-ticket)
- Planning a batch
- Lanes
- Working a batch (work-tickets, ticket-worker)
- Settling a batch
- Converting `batch:<area>` labels

## Where parents live

| `mode` | Parent | Children |
| --- | --- | --- |
| `epics` (GitLab) | A group epic in the board's group | Issues attached with the epic as their parent |
| `sub-issues` (GitHub) | An issue in the children's repo, off the board | Its sub-issues |
| `labels` (either) | An open issue titled `Batch: <area>` carrying the `batch:<area>` label | The other open issues carrying that label |

In `epics` and `sub-issues` mode, run the adapter's parent operations: **list-parents**,
**read-parent**, **create-parent**, **attach-child**, **comment-parent**,
**read-parent-item** and **close-parent**. In `labels` mode they are built from operations
every adapter has:

- **list-parents**: **list-open-issues**, then group by `batch:<area>` label. The parent is
  the issue titled `Batch: <area>` with that label; every other issue with the label is a
  child. A label with children but no parent issue gets one from **create-parent**.
- **read-parent**: the ticket's `batch:<area>` label names its batch; its parent is that
  batch's parent. A ticket with two `batch:` labels is reported under Needs Attention and
  treated as a single until a person fixes it.
- **create-parent**: **ensure-label** `batch:<area>` (color `5319e7`, description
  `Batch: <area>`), then **create-issue** titled `Batch: <area>` with that label. Do not
  add it to the board on GitHub; on GitLab it shows on the board and is skipped as a parent.
- **attach-child**: **remove-label** any other `batch:` label, then **add-label**
  `batch:<area>`.
- **comment-parent**, **read-parent-item**, **close-parent**: **comment**, **read-issue**,
  **close-issue** on the parent's number.

`<area>` is a short lower-case slug (`dev-environments`, `select-ui`).

## What a parent is not

A parent is never a ticket. It is not triaged, audited, prioritized by itself, given a
run or model label, or dispatched. Drop every parent (any issue **list-parents** returned
as a parent) from the board items before triage, and count them separately in the summary.
Its priority is its highest child's, and its lane is its children's (see Lanes).

## Forming batches (daily-grooming)

Run after priorities are set (grooming step 3) and before lanes are triaged. Candidates
are the open tickets in the backlog and ready lanes that have no parent. These stay
single, always:

- a ticket with the blocked label or in the blocked lane;
- a migration: it carries a `migration` label, or its plan or body names a schema
  migration or a file under a migrations folder;
- a security-sensitive ticket: authentication, authorization, secrets, permissions,
  cryptography, or personal data (a `security` label, or the plan or body says so);
- a ticket with `run:solo` (no code to batch).

Two tickets **fit** when all of these hold:

1. **Same repo** (the owning repo; see registry-rules.md).
2. **Same area**: they share a `component:<x>` or `rmf:<x>` label, or the files their plans
   name overlap. No area signal means no fit; never batch on title words alone.
3. **Compatible priority**: their priority roles are at most one rank apart (P1 with P2,
   never P1 with P3), so a high ticket is never held behind low ones.

Then, for each candidate, in priority order:

1. **Attach to an open parent that fits.** A parent fits when every child it has fits the
   candidate, it has fewer than `size` children open, and no child is in the in-progress
   or review lane (a batch being worked takes no new children). Several fit: the one with
   the most children. **attach-child**.
2. **Else form a new batch** from the candidate and the other unparented candidates that
   fit it and each other, up to `size`, highest priority first. Only two or more make a
   batch; a ticket with no partner stays single. **create-parent** with the title
   `<Area>: <what the children have in common>` and a body naming the area, the rule that
   formed it and the children, then **attach-child** each.

Act without asking. List every attach and every created parent in the summary under
**Batches**, each as `parent <ref> <title>: +#<child> ...`. With `--dry-run`, list the
same without running any write.

## Joining a batch (write-ticket, plan-ticket)

A newly filed ticket, or one just planned, joins an open parent that fits it under the
rules above (attach only; never create a parent here). No parent fits: it stays single
until the next grooming pass. Say which parent it joined, or that it stayed single.
`plan-ticket` judges the fit before it posts: a ticket that joins a batch gets its plan
on the parent (an addendum, or the whole batch's plan), never on itself.

## Planning a batch

The plan for a batch is written on the **parent** with **comment-parent** and covers every
child: one section per child (`### #<n> <title>`) in the order the worker should take them,
plus what they share (files, the test command, the order's reason). It is the same plan
shape as a single's (plan-one-ticket.md), once per child, under one `### Final Plan`; the
word cap applies to each child's section.

- Planning any child plans its whole batch: read every child (and **read-parent-item** for
  the parent's earlier plan) and post one plan covering them all.
- A child that joins after the parent's plan was posted needs an addendum on the parent
  (`### Final Plan addendum: #<n>`) before the batch counts as planned again.
- A child's own comments still hold anything specific to it (a `Blocked:` note, a
  model-fit note); the plan does not live there.

## Lanes

Lanes stay on the children; the board shows children. Children follow their parent:
a batch is **ready** when the parent's plan covers every open child and no child is
blocked, and then grooming moves every open child to the ready lane together. Until then,
every child stays in (or goes back to) the backlog lane. Any child in the in-progress or
review lane holds the whole batch where it is. A batch whose children are all P3 (or
deferred) waits in the backlog like a P3 single; one higher child lets it move.

## Working a batch (work-tickets, ticket-worker)

`work-tickets` reads each ready ticket's parent (**read-parent**) and groups ready tickets
by parent. Each parent with ready children is **one slot and one worker**; a ticket with
no parent is a single slot as before. The batch slot carries the parent and its ready
children in the plan's order. Its model is the strongest tier any child's model label
names (frontier over workhorse over fast), and its effort the highest `effort:` label
among them (low, medium, high, xhigh, max). A child that fails a dispatch check (no model
or run label, not covered by the plan) is skipped and named; the rest of the batch goes.
A direct `ticket-worker` run on any child works the batch: every open child assigned to
the user, not blocked, and covered by the plan.

The worker works the children **in order in one worktree, on one branch** named for the
parent (`batch/<parent number>-<area>`; the number is the parent's issue number or epic
iid, and `<area>` its `batch:<area>` label, else the slug of its title before the colon),
and opens **one** pull or merge request:

- It moves each child to in progress when it starts that child, and every finished child
  to review when the request opens.
- A child's commits say `Refs #<child>`; closing keywords go only in the request body,
  so a child dropped late is never closed by a commit already on the branch. Each finished
  child gets `Closes #<child>` there (the same form a single uses).
- A child it could not finish is left out of the closing keywords, gets a comment saying
  why, and goes to the blocked lane with the blocked label; the other children still
  ship. Its uncommitted work is saved as a patch beside the worktree and named in that
  comment, and its commits are reverted.
- A child that needs a live action makes the whole request a held review with no closing
  keywords; that child's `Blocked: live action` comment names the children to close by
  hand after the merge.
- The parent is only referenced (`Refs <parent>`), unless every open child of the parent
  closes in this request: then the request closes the parent too where the tracker can
  (GitHub and `labels` mode: `Closes #<parent>`). A GitLab epic cannot be closed by a
  merge request keyword, so grooming closes it (next section).
- The request body lists every child as a checklist, ticked for the ones it closes.
- The result is `review_opened` once the request opens, even with some children held;
  it carries `parent` and each child's outcome (`children_status`).

## Settling a batch

In grooming's settle step, after children are settled: **close-parent** every open parent
whose children are all closed, with a comment naming them. A parent with no children left
at all (all moved elsewhere) is closed the same way.

## Converting `batch:<area>` labels

`daily-grooming --convert-batch-labels` turns existing `batch:<area>` labels into parents,
once, in `epics` or `sub-issues` mode (in `labels` mode the labels already are the
batches). For each repo, for each `batch:<area>` label on open issues:

1. Reuse an existing parent: in `sub-issues` mode an open issue carrying the label that
   has sub-issues or is titled `Batch: <area>`; in `epics` mode an open epic titled
   `Batch: <area>`. Else **create-parent** titled `Batch: <area>`.
2. **attach-child** each open issue with the label, highest priority first. Beyond `size`
   children, the rest go to a further parent `Batch: <area> (2)`, and so on. The singles
   rules do not apply here: the team already chose these batches.
3. **remove-label** the `batch:<area>` label from each child once its attach succeeded, so
   the label and the parent cannot disagree later.

List every parent and attach in the summary. With `--dry-run`, list them without writing.
Without the flag, grooming never converts labels.
