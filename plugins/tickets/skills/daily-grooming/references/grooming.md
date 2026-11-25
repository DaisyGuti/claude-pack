# The grooming pass

Run every step in order and do not ask for confirmation between steps. Finish the whole
pass, then print the summary. The tracker, board, lanes, priorities, labels, model
labels and repos come from the registry (`registry.py show`). Every tracker action is a named
operation shown in bold; the commands are in `trackers/<tracker>.md` for the registry's
tracker. Read that one file once and run each operation as written. `<scripts>` and `<data>`
are the two paths printed at the top of SKILL.md.

The board is shared. Grooming never changes an assignee, never closes or deletes an
issue (the one exception: with batching on, a batch parent that has children, all closed),
and never moves a ticket that a worker or a person put somewhere (step 4 lists them).

**Batching.** `registry.py show` prints `batching` (`mode`, `size`). With `mode` `off`, skip
every paragraph below marked "when batching is on", and `--convert-batch-labels` changes
nothing and says so. Otherwise read the plugin's `references/batches.md` in full; the batch
steps follow it, and the parent operations (**list-parents**, **create-parent**,
**attach-child**, ...) are built as it says for `mode`.

## Contents

- 0. Set up
- 1. Fetch the board, and settle finished work first
- 2. Flag duplicates
- 3. Audit each open ticket (with the priority sync)
- 3b. Group before splitting (when batching is on)
- 4. Triage the lanes
- 5. Order the Ready lane
- 6. Apply the changes
- 7. Make every Ready ticket dispatchable
- 8. Print the summary

## 0. Set up

1. Read the registry (`registry.py show`). **auth-check** must pass, or stop and say so.
2. Resolve the board per `registry-rules.md` ("Resolving a project board argument").
3. **capture-board** gives `tracker_ids`, `missing_lanes`, `missing_priorities`,
   `has_priority` and, on GitHub, `priority_mode`. Stop and print the raw output when the
   ready lane is missing. A
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

**Parents, when batching is on.** Run **list-parents** (per repo, or once for the board's
group, as the adapter says) and keep each parent with its children. It returns batch parents
only (titles starting with `Batch: `; batches.md, "A batch parent's title"): any other parent,
a roadmap epic or a tracking issue, is not touched by the batch steps, and one that is on the
board is an ordinary item. In `labels` mode, list each `batch:<area>` label that has children
but no parent issue under Needs Attention; step 3b makes its parent. With
`--convert-batch-labels`, convert the labels now (batches.md, "Converting `batch:<area>`
labels"; in `labels` mode it changes nothing and says so), and treat the parents it made or
would make as parents for the rest of the pass. Then drop every parent from the items before
anything else looks at it (batches.md, "What a parent is not") and count them for the
summary. Each remaining item's parent, if any, is the one whose children include it.

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

5. When batching is on, after the items are settled: **close-parent** every open batch
   parent that has at least one child and whose children are all closed (batches.md,
   "Settling a batch"). A parent with no children is left open.

A finished item is done and goes no further: no audit, no priority, no triage, and
above all no plan. Planning shipped work fills the ticket with a plan for something
already built. Count them for the summary. Everything still open continues.

(A board workflow that moves closed items to done on its own leaves step 1 nothing to
do. It stays because a workflow that is off, or an issue closed while it was off,
leaves exactly this backlog behind.)

## 2. Flag duplicates

Flag open tickets with near-identical titles or bodies, within a repo or across repos,
and close candidates: tickets that merged work or another ticket already settles. Never close
or merge them. List each group under Duplicates to Review.

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
  `ticket-labels.md`, "Blocked").
- **The blocked label and the blocked lane agree, both ways.** An open ticket with the
  blocked label in any lane but the blocked one moves to the blocked lane (**set-lane** with
  role `blocked`, in step 6), whatever lane it sat in. A ticket in the blocked lane without
  the label gets it back (**add-label**) when its latest status comment begins `**Blocked:`;
  without one it goes under Needs Attention and stays where it is.
- **The dependency report.** Write every open issue from step 1 (`ref`, `repo`, `state`,
  `title`, `body`) to a temporary JSON file as `<scripts>/deps.py`'s docstring says, with
  `children` for each batch parent (when batching is on). Run **merged-reviews** on each open
  issue some ticket names on a `Depends on:`, `Blocked by:` or `Blocked on:` line, and add its
  URLs as `merged_reviews`. Run `<scripts>/deps.py <file>`. For each ref under `unknown`, run
  **issue-state**, add it with its state, and run it again; exit 2 means bad input: fix the
  file and run it again. Delete the file after (a `--dry-run` writes and deletes it too). Then:
  - each **cycle** goes under Needs Attention as its chain (`#26 depends on #21, #21 closes
    after its part #32, #32 depends on #26`), with the re-point that breaks it: the
    `Depends on:` link that names a tracker or a ticket it was cut from, pointed at the part
    that does the work;
  - each **tracker dependency** goes under Needs Attention as `#<ticket> names <tracker or
    parent>; name <name_instead> instead`, or with its `open_parts` to choose from when
    `name_instead` is null;
  - each **merged dependency** goes under Needs Attention with its reviews: a person reads them
    and either closes the issue (its work is done) or keeps it named (more is to come);
  - **cleared** is the next item.

  Grooming never edits a `Depends on:` line itself: a person, or the next plan of that
  ticket, makes the re-point.
- **Dependency holds that have cleared.** A ticket under `cleared` whose most recent
  `**Blocked:` comment has the kind `dependency` (a merged review closes its issue, so this
  is how review-landed work frees what waits on it): **remove-label** the blocked label,
  **comment** "Unblocked: every dependency is closed.", and in the same step move it out of
  the blocked lane through step 4's table like any open ticket. Any other kind of hold stays
  for a person.
- **Stale reviews.** An open ticket in the review lane that no open review from step 1 closes
  is stale: list it under Needs Attention (its review merged without closing it, or was
  closed), and leave its lane.

**Label preservation.** Grooming removes a label in exactly two cases: a priority label
it is replacing, and the blocked label of a dependency hold whose dependencies are all
closed (above), which leaves the blocked lane in the same step. It never removes a `model:*`, `repo:*`, `project:*`, `size:*` or run
label, or any other label it did not add. The one place a run label is ever removed is
the planning step's correction, from the plan's evidence. When in doubt, add; do not
remove.

### Priority

One role per ticket from the registry's Priority table, judged by its Meaning column
and by the ticket's repo brief: work on the critical path the brief describes is a
P1 candidate. When the call is close, say in the summary which brief section or
reason decided it. The role names come from the registry.

- **GitHub in field mode** (**capture-board**'s `priority_mode`). The field and a label
  named exactly like the field's option are kept in step, and the field wins.
  - Field set: the label is added if missing (**ensure-label** with the priority
    label's color and description from ticket-labels.md, then **add-label**), and any other priority label
    is removed (**remove-label**).
  - Field empty, exactly one priority label: **set-priority** from that label.
  - Neither, or several labels and no field: judge it, set both, and note the
    reasoning.
- **GitLab, or GitHub in label mode** (no Priority field, or one with no options). The
  priority is one label, so the ticket must carry exactly one priority label. None: judge
  it. Several: judge it, keep one, and note the reasoning. **set-priority** swaps the
  others out on both trackers.
- A priority value in `missing_priorities` is skipped, with one warning for the run.

## 3b. Group before splitting (when batching is on)

Now that every ticket has its priority, group related tickets before step 8 splits the waves:
a parent takes one place in a wave and carries all its children's files, so grouping first
leaves fewer units to schedule and folds most file overlaps inside one batch. Look across the
backlog and ready lanes, in two passes.

1. **Batches.** Form batches as batches.md says ("Forming batches"): attach each fitting
   unparented candidate to an open parent, else form new parents from candidates that fit
   each other, never a batch of one. The singles rules there hold. The labels are already
   fetched; run **read-issue** for a candidate's plan only when its labels give no area
   signal. In `epics` and `sub-issues` mode run **read-parent** on each candidate first: one
   with any parent (a non-batch one, `batch` false) is not a candidate, since attaching it
   would re-parent it. In `labels` mode, also decide a `Batch: <area>` parent for each
   `batch:<area>` label step 1 listed without one.
2. **Parents.** In `epics` and `sub-issues` mode, a planned ticket that stayed single, has no
   parent and whose body (fetched in step 1) names an open epic or parent is attached to it
   as `plan-one-ticket.md` step 4 item 5 says. An unplanned ticket is left to step 7, whose
   planning attaches it the same way.

Here you only decide: step 6 runs **create-parent** and **attach-child** (a `--dry-run` lists
them), and from now on a ticket you attach counts as that parent's child.

## 4. Triage the lanes

**Held tickets keep their lane.** A ticket is held when it is in the in-progress lane,
in the blocked lane, in the done lane while still open, carries the blocked label, or
appears in the `closes` list of an open review from step 1. A worker or a person put it
there; leave its lane exactly as it is. It is still audited and given a priority (step
3), and it is never planned. List a ticket sitting in the done lane while open under
Needs Attention.

A ticket whose dependency hold step 3 cleared in this run is no longer held, even in
the blocked lane: it goes through the table below like any other open ticket, so the label
comes off and the lane changes together. One more exception: a ticket that carries the blocked
label outside the blocked lane moves to the blocked lane (step 3), from the ready, backlog,
in-progress or review lane alike, and keeps its label and comment. A labelled ticket never
waits in the backlog.

**Ready means planned.** A ticket goes to the ready lane only with a `### Final Plan` comment
and no open blocker, and a planned, unblocked ticket always goes there, never left in the
backlog. The list from step 1 carries no comments, so run **read-issue** on each ticket the
table would otherwise send to ready, and look for the plan.

**Batches, when batching is on.** Children move together (batches.md, "Lanes"). Run
**read-parent-item** for each parent with an open child: the batch is planned when its
`### Final Plan` (with any `### Final Plan addendum: #<n>`) has a section for every open
child. A planned batch with no blocked child sends every open child to ready; otherwise every
child that is not held goes to (or stays in) the backlog lane. A child in the in-progress or
review lane, or in the `closes` list of an open review, holds the whole batch where it is: no
child of it moves. A batch is
deferred, and its children go to the backlog, only when every child is a P3 or deferred. The
table below is for singles.

For everything else (the open tickets that are not held):

| Condition | Lane |
| --- | --- |
| A P3, or the repo's brief marks it deferred or outside the current work | backlog |
| Planned, with no open blocker | ready |
| Not planned yet | backlog until step 7 plans it; a ticket already in ready stays there until then |

## 5. Order the Ready lane

The tickets step 4 sent to ready, and the ones step 7 will plan into it, and only those, are
ordered for the summary: by the Priority table's rank, highest first; within a rank, tickets
that other open tickets name on a `Depends on:` line first, then the ticket number ascending.
When batching is on, a batch is one entry, ranked by its highest child.
There is no cap on the order. Step 8 cuts it into waves, once step 7 has made every plan
readable.
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
something: **ensure-label** for each label that may be missing; when batching is on, each
**create-parent** of step 3b and then each **attach-child**; **set-priority** and the
label adds and removes; **set-lane**. A failed write goes under Needs Attention with the
tracker's error, and the run goes on to the next change; never retry one in a loop.

## 7. Make every Ready ticket dispatchable

After the lanes are set, a Ready ticket is dispatchable when it has a plan, a priority,
one model label and one run label. For every ticket in the ready lane that is not held, and
every other unplanned, unblocked ticket step 4 left in the backlog, board-wide (not only the
ones assigned to the person running this):

1. **read-issue**. A `### Final Plan` comment means it is planned.
2. **Unplanned:** plan it by `plan-one-ticket.md`. The model label is sized to the plan's
   scope as `ticket-labels.md` says. Posting the plan moves the ticket to the ready lane
   unless it is blocked; a ticket the planning holds goes to the blocked lane.
3. **Planned, but missing a model or run label:** labels-only mode of the same file.

When batching is on, a batch is planned as one unit, on its parent, by that file's "Batches"
section: one plan covering every open child when the parent has none, or an addendum for each
child its plan does not cover. It counts as one ticket below, and its brief also names the
parent's ref and each child's Remote and number. The labels-only mode stays per child.
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
    file); which mode to run; and the instruction to change no priority or assignee, and to move the
    lane only as `plan-one-ticket.md` says.
  - **What it returns.** Only the one-line result `plan-one-ticket.md` defines, with its
    word count. No plan text, no logs.
- Re-run once, yourself, any ticket whose plan came back over 200 words (a batch: any child's
  section) or whose child failed in a way that looks like a weak run. Any other failure goes
  under Needs Attention with the child's reason.

Tickets that come back `held` or `could not plan` go under Needs Attention with the
reason. The notes on a `planned` line go in the summary too: duplicates and close candidates
under Duplicates to Review, a proposed batch under Batches, a milestone set in Counts, and a
suggested parent, a milestone mismatch or no assignee under Needs Attention. In a `--dry-run` this step only lists the tickets that would be planned or
labelled.

## 8. Print the summary

Plain language, short, grouped under these headings, each with its count:

- **Moved to Done**: the finished items step 1 settled.
- **Batches** (when batching is on): what step 3b grouped: every attach (to an epic or a
  batch parent) and every created parent, each as
  `parent <ref> <title>: +#<child> ...`, then the parents closed in step 1 and the labels
  converted, and the count of parents left out of triage. A `--dry-run` lists what it would do.
- **Duplicates to Review**: each group with ticket numbers and titles.
- **Ready (in waves)**: `#N title [priority] [repo]`, marked planned, already planned, or
  labelled, and with the reasoning for any priority that was a close call. The waves come
  from `<scripts>/waves.py`, never from a split by hand; its docstring holds the rules and
  the input shape. Write the step 5 order as that JSON to a temporary file (a local file, so
  a `--dry-run` writes it too): one entry per unit, a batch as its parent with every child's
  labels and refs, and the label `migration` added to a unit whose plan names a schema
  migration. Run `<scripts>/waves.py <file> --pool <N>`, `<N>` being `work-tickets`'
  `--max-parallel` (5 by default), print its waves in order and delete the file. Exit 2 means
  bad input: fix the file and run it again. A unit under `no_files` runs alone and goes under
  Needs Attention, since its plan names no **Files to touch**. When batching is on, a batch
  is one line, `parent <ref> <title>: #<child> ...`.
- **Backlog (priority order)**: `#N title [priority]` and the reason it is in the
  backlog.
- **In progress**: `#N title`, with its review link when it has one.
- **Blocked**: `#N title`, what it waits on from its `Blocked:` comment, and its review
  link when it has one. Then the lane moves the label sync made, and the holds cleared.
- **Needs Attention**: everything grooming could not settle by itself, each with the
  ticket and the one thing someone must do: unplanned or unlabelled tickets and why,
  missing context files, a missing lane or priority on the board, repos not in the
  registry, closed-but-unmerged reviews, tickets in the done lane that are open,
  abandoned or contradictory labels, descriptions with no acceptance criteria, failed
  writes, Ready tickets with no assignee (`work-tickets` will not pick those up), and step 3's
  dependency report (cycles, tracker dependencies, merged dependencies, stale reviews), each
  with the re-point to make.
- **Counts**: plans that already existed, plans written, labels added, milestones set from a
  parent, tickets held.
