# The grooming pass

Run every step in order and do not ask for confirmation between steps. Finish the whole
pass, then print the summary. The tracker, board, lanes, priorities, labels, model
labels and repos come from the registry (`registry.py show`). Every tracker action is a named
operation shown in bold; the commands are in `trackers/<tracker>.md` for the registry's
tracker. Read that one file once and run each operation as written. `<scripts>` and `<data>`
are the two paths printed at the top of SKILL.md.

The board is shared. Grooming never changes an assignee, never closes or deletes an
issue, and never moves a ticket that a worker or a person put somewhere (step 4 lists
them).

## Contents

- 0. Set up
- 1. Fetch the board, and settle finished work first
- 2. Flag duplicates
- 3. Audit each open ticket (with the priority sync)
- 4. Triage the lanes
- 5. Order the Ready lane
- 6. Apply the changes
- 7. Make every Ready ticket dispatchable
- 8. Print the summary

## 0. Set up

1. Read the registry (`registry.py show`). **auth-check** must pass, or stop and say so.
2. Resolve the board per `registry-rules.md` ("Resolving a project board argument").
3. **capture-board** gives `tracker_ids`, `missing_lanes`, `missing_priorities` and
   `has_priority`. Stop and print the raw output when the ready lane is missing. A
   missing backlog or done lane means the moves to it are skipped and listed under
   Needs Attention. A missing priority value, or no Priority field, is handled in
   step 3.
4. Read each `--context FILE` end to end. A file missing on disk goes under Needs
   Attention and the run continues without it. Each repo's own brief (`registry-rules.md`,
   "Resolving a ticket's product brief") is read the first time a priority is judged
   or a ticket is planned for that repo, once per repo; never one brief for a board
   that spans several products.

## 1. Fetch the board, and settle finished work first

Run **list-items** (all lanes). Keep issue items and review items; draft items are
left alone. Drop, and list under Needs Attention, any item whose repo is not in the
registry's table, and with `--repo` any item outside the named repos: a repo missing
from the table is invisible by design.

Real state decides. An item whose lane was never set reads as "not done"
while its issue is closed and shipped. For each registry repo on the board:

1. **list-open-issues** and **list-open-reviews** for the repo. Keep the result for the
   rest of the run: it carries each open issue's body and labels (used in steps 2 and 3)
   and which issues an open review closes (used in step 4).
2. An issue item whose number is not in the open list may be closed. Confirm each with
   **issue-state**; a closed one is finished.
3. A review item whose number is not in the open reviews: **review-state**. A `merged`
   one is finished. A `closed` one was abandoned: leave it and list it under Needs
   Attention.
4. For every finished item whose lane is not already done, **set-lane** to done.
   On a tracker whose **list-items** lists open issues only (the adapter says so;
   GitLab does), also run it for closed issues as the adapter describes, and move
   each one still in a lane other than done.

A finished item is done and goes no further: no audit, no priority, no triage, and
above all no plan. Planning shipped work fills the ticket with a plan for something
already built. Count them for the summary. Everything still open continues.

(A board workflow that moves closed items to done on its own leaves step 1 nothing to
do. It stays because a workflow that is off, or an issue closed while it was off,
leaves exactly this backlog behind.)

## 2. Flag duplicates

Flag open tickets with near-identical titles or bodies, within a repo or across repos.
Never close or merge them. List each group under Duplicates to Review.

## 3. Audit each open ticket

Check, using the bodies and labels already fetched:

- **A clear description or acceptance criteria.** One that has neither goes under
  Needs Attention.
- **Priority** (below).
- **Semantic labels** (`bug`, `enhancement` or whichever the repo uses). Run
  **list-labels** once per repo and add one you can determine from the ticket with
  **add-label**, only when the repo already has that exact label. Never invent one.
- **Run label.** One carrying both run labels is a contradiction only a person can
  settle: report it under Needs Attention and change nothing. A Ready ticket with
  neither gets one in step 7, from the plan it writes; it is reported only if that step
  could not.
- **Held work.** A ticket with the blocked label but no `Blocked:` comment: run
  **read-issue** and look for a comment that begins `**Blocked:`. Without one, list it
  under Needs Attention, so someone asks what it waits on (see
  `ticket-labels.md`, "Blocked"). A ticket in the blocked lane
  without the blocked label goes there too.
- **Dependency holds that have cleared.** A ticket whose most recent `**Blocked:`
  comment has the kind `dependency`: check each issue on its `Depends on:` line with
  **issue-state**. When every one is closed (a merged review closes its issue, so
  this is how review-landed work frees what waits on it), **remove-label** the
  blocked label and **comment** "Unblocked: every dependency is closed." If it
  sits in the blocked lane, it moves to the ready lane in step 4. Any other kind of
  hold stays for a person.

**Label preservation.** Grooming removes a label in exactly two cases: a priority label
it is replacing, and the blocked label of a dependency hold whose dependencies are all
closed (above). It never removes a `model:*`, `repo:*`, `project:*`, `size:*` or run
label, or any other label it did not add. The one place a run label is ever removed is
the planning step's correction, from the plan's evidence. When in doubt, add; do not
remove.

### Priority

One role per ticket from the registry's Priority table, judged by its Meaning column
and by the ticket's repo brief: work on the critical path the brief describes is a
P1 candidate. When the call is close, say in the summary which brief section or
reason decided it. The role names come from the registry.

- **GitHub with a Priority field.** The field and a label named exactly like the
  field's option are kept in step, and the field wins.
  - Field set: the label is added if missing (**ensure-label** with color `ededed` and
    description `Priority: <name>`, then **add-label**), and any other priority label
    is removed (**remove-label**).
  - Field empty, exactly one priority label: **set-priority** from that label.
  - Neither, or several labels and no field: judge it, set both, and note the
    reasoning.
- **GitLab, or GitHub with no Priority field.** The priority is one label, so the ticket
  must carry exactly one priority label. None: judge it. Several: judge it, keep one,
  and note the reasoning. **set-priority** on GitLab already swaps the others out; on a
  GitHub board with no field, use **ensure-label**, **add-label** and **remove-label**.
- A priority value in `missing_priorities` is skipped, with one warning for the run.

## 4. Triage the lanes

**Held tickets keep their lane.** A ticket is held when it is in the in-progress lane,
in the blocked lane, in the done lane while still open, carries the blocked label, or
appears in the `closes` list of an open review from step 1. A worker or a person put it
there; leave its lane exactly as it is. It is still audited and given a priority (step
3), and it is never planned. List a ticket sitting in the done lane while open under
Needs Attention.

A ticket whose dependency hold step 3 cleared in this run is no longer held, even in
the blocked lane: it goes through the table below like any other open ticket.

For everything else (the open tickets that are not held):

| Condition | Lane |
| --- | --- |
| A P3, or the repo's brief marks it deferred or outside the current work | backlog |
| Anything else | ready |

## 5. Order the Ready lane

The tickets step 4 sent to ready, and only those, are ordered for the summary: by the
Priority table's rank, highest first; within a rank, tickets that other open tickets
name on a `Depends on:` line first, then the ticket number ascending. There is no cap.
A ticket step 4 held or left alone is not in this order and its lane is not touched
here, wherever its priority would rank it: a worker moves a ticket to in-progress the
moment it claims it, and changing its lane here would un-claim work in flight. When a
ticket's step 4 outcome is unclear, leave its lane alone and put it under Needs
Attention.

No tracker operation reorders a lane, so the order is reported for someone to apply by hand.

A Ready ticket with no assignee, whether it was promoted today or was already there, goes
under Needs Attention: `work-tickets` works only tickets assigned to its person, and
grooming never assigns.

## 6. Apply the changes

Everything above only decides. Now carry it out, or in a `--dry-run` print it.

**`--dry-run`:** read-only operations only (the steps above already ran them). Print
every change grouped by ticket: lane moves, priority sets, labels added and removed,
labels that would be created, and each ticket that would be planned or labelled. Run no
write operation and spawn nothing. Then print the summary as if the changes had been
made, marked as planned.

**Otherwise,** apply in this order, running an operation only when it changes
something: **ensure-label** for each label that may be missing; **set-priority** and the
label adds and removes; **set-lane**. A failed write goes under Needs Attention with the
tracker's error, and the run goes on to the next change; never retry one in a loop.

## 7. Make every Ready ticket dispatchable

After the lanes are set, a Ready ticket is dispatchable when it has a plan, a priority,
one model label and one run label. For every Ready ticket that is not held, board-wide
(not only the ones assigned to the person running this):

1. **read-issue**. A `### Final Plan` comment means it is planned.
2. **Unplanned:** plan it by `plan-one-ticket.md`.
3. **Planned, but missing a model or run label:** labels-only mode of the same file.
4. **Several model labels:** list under Needs Attention; `work-tickets` will not
   dispatch it.

**How many at once.** Count the tickets from items 2 and 3.

- Up to three: do them yourself, one after another.
- More than three: spawn them as subagents, one ticket each, in batches, waiting for
  each batch before the next.
  - **Batch size.** Four. Send the batch's Agent calls in one message with
    `run_in_background: false`, so every result of the batch returns together. If a spawn is
    refused for hitting Claude Code's concurrent-subagent limit, run that ticket after a
    child in the batch returns.
  - **Model and effort.** Set `subagent_type` to `general-purpose` and `model` to `sonnet`
    explicitly on every spawn, never inherited (`model-selection.md`: planning is
    spec-driven work, the `workhorse` tier). Raise one ticket to `opus` only when a plan
    came back weak.
  - **The brief.** A subagent has none of your context, so each brief stands alone: the
    absolute paths of `plan-one-ticket.md`, `registry-rules.md`, `ticket-labels.md` and the
    tracker adapter file; the `<scripts>` and `<data>` paths; the ticket's repo Remote and
    number; the repo's brief and local clone paths from the registry (or the `--context`
    file); which mode to run; and the instruction to change no lane, priority or assignee.
  - **What it returns.** Only the one-line result `plan-one-ticket.md` defines, with its
    word count. No plan text, no logs.
- Re-run once, yourself, any ticket whose plan came back over 200 words or whose child
  failed in a way that looks like a weak run. Any other failure goes under Needs
  Attention with the child's reason.

Tickets that come back `held` or `could not plan` go under Needs Attention with the
reason. In a `--dry-run` this step only lists the tickets that would be planned or
labelled.

## 8. Print the summary

Plain language, short, grouped under these headings, each with its count:

- **Moved to Done**: the finished items step 1 settled.
- **Duplicates to Review**: each group with ticket numbers and titles.
- **Ready (priority order)**: `#N title [priority] [repo]`, marked planned, already
  planned, or labelled, and with the reasoning for any priority that was a close call.
- **Backlog (priority order)**: `#N title [priority]` and the reason it is in the
  backlog.
- **In progress**: `#N title`, with its review link when it has one.
- **Blocked**: `#N title`, what it waits on from its `Blocked:` comment, and its review
  link when it has one.
- **Needs Attention**: everything grooming could not settle by itself, each with the
  ticket and the one thing someone must do: unplanned or unlabelled tickets and why,
  missing context files, a missing lane or priority on the board, repos not in the
  registry, closed-but-unmerged reviews, tickets in the done lane that are open,
  abandoned or contradictory labels, descriptions with no acceptance criteria, failed
  writes, and Ready tickets with no assignee (`work-tickets` will not pick those up).
- **Counts**: plans that already existed, plans written, labels added, tickets held.
