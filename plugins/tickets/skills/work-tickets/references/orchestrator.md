# Ready-ticket orchestrator

Process the **Ready** tickets of a project board, on GitHub or GitLab, that are assigned to
the person running this command, by starting `tickets:ticket-worker` subagents from a rolling
pool of parallel workers. The tracker, board, lane names, labels and repos come from the
registry, which is the only place any of them is written down. `<scripts>` and `<data>` are the two paths printed at
the top of SKILL.md, which also links `registry-rules.md`, `ticket-labels.md`,
`model-selection.md` and `agents/ticket-worker.md` by absolute path.

**Whose tickets.** The person running the command is whoever is signed in to the tracker CLI
on this machine (**current-user**, resolved once in Phase 1). Only Ready tickets assigned to
that login are worked. Unassigned tickets and tickets assigned only to others are left exactly
as they are and counted in the report. There is no flag for working someone else's tickets: to
do that, sign in as them.

**Tracker operations.** Every action on the tracker below is a named operation, shown in bold
(**list-items**, **set-lane**, ...). The exact commands for each are in
`references/trackers/<tracker>.md` for the registry's tracker. Read that one file in full
before Phase 1 and run each operation as written there; never improvise a command for one. A
**review** is a pull request on GitHub and a merge request on GitLab.

## Contents

- Invocation
- Labels a ticket must carry
- Mechanics
- The run record
- Phase 1: capture the board
- Orchestration (steps 1 to 8)
- Notes

## Invocation

```text
/tickets:work-tickets                          # every Ready ticket across the default board
/tickets:work-tickets --dry-run                # the queue and nothing else
/tickets:work-tickets --priority P1            # only P1 tickets
/tickets:work-tickets --project 2 --owner me   # a different board (a pasted board URL works too)
/tickets:work-tickets --max-parallel 8         # a bigger pool
```

No arguments are needed, and you never ask the user for a project number or a repo list.
Defaults, applied when the flag is absent:

- **tracker, host, board:** the registry's Tracker and Board sections
- **repos:** every repo in the registry's table; keep no list here
- **priority:** no filter; any priority, and none, is eligible
- **max-parallel:** 5, the number of workers kept running at once. **limit:** 30

Overrides:

- `--priority P0|P1|P2|P3`, repeatable: priority roles from the registry's Priority table. It
  narrows within Ready and never replaces it.
- `--project N` / `--owner OWNER`, or a pasted board URL of either tracker, per
  `registry-rules.md` ("Resolving a project board
  argument").
- `--repo NAME`, repeatable, restricting the run to those registry repos.
- `--context FILE`, repeatable: the brief used for plan validation. Absent, each worker gets
  its own repo's brief from the registry.
- `--max-parallel N`, `--limit N` (each minimum 1), `--dry-run`, `--clear-skipped`.

A ticket's lane equal to the registry's ready lane value, and the signed-in login among its
assignees, are always the gate.

## Labels a ticket must carry

A ticket missing either set was never groomed and is not dispatched.

**A model label** picks the worker's model. Run
`<scripts>/resolve_model.py --registry <data>/registry.md <every label on the ticket>`; it
reads the registry's Model labels table and prints `tier`, `model` and `effort`. Its exit
codes: 3 is no model label (`reason="no model label"`), 4 is conflicting labels, 5 is a
`model:` label that maps to no tier (`reason="unrecognized model label: <value>"`). These
tickets are not dispatched; record each with `ticket_state.py skip` and the reason, and list
it under "Not dispatched" in the report.

**`effort:<level>`** (optional) sets the worker's reasoning effort; the resolver passes it
through.

**The run-worker label or the run-solo label** (registry Labels roles `run_worker` and
`run_solo`), exactly one.

- run-worker: a worker can finish it end to end, and it is self-contained. That is what makes
  it safe to run beside the others in the pool. It keeps the label even when its last step is
  a live action no worker can take; the worker builds the rest and stops at
  `needs_manual_action`.
- run-solo: nothing to build at all. Skipped, never dispatched.
- Neither: not dispatched, `reason="no run label: ticket has not been groomed"`.

`ticket-labels.md` has the full rule for both labels.
Concurrency safety is a per-ticket property decided when the ticket is groomed (the
run-worker label means self-contained), so there is no pairwise conflict check here.

## Mechanics

- **Board key.** On GitHub `<owner>-<number>`. On GitLab the board's group or project path, a
  hyphen, then the board id (or the board name lower-cased when the registry gives only a
  name). `<login>` is the signed-in login from **current-user**. Every `ticket_state.py` call
  takes `--data-dir <data> --board-key <board key> --login <login>`; its file name replaces
  each `/` and space with a hyphen.
- **Worktrees.** Each worker works in its own git worktree. It uses the throwaway worktree
  Claude Code gives it for the repo your session started in, and makes
  `<data>/worktrees/<board key>-<login>/<slot id>/<repo>` for every other repo. Pass that
  folder as `worktree_root` in the dispatch message.
- **Pushes.** Every worker lands its change by review, whatever the repo's own rules say: it
  pushes its own branch, never the default branch, and opens a pull or merge request with no
  blocked label. The ticket ends `review_opened`, a successful end, and merging the review
  closes the issue. No worker closes an issue or moves a card to done; `daily-grooming` settles
  closed issues to done. A ticket that ends in `needs_manual_action` pushes its own branch and
  opens a review carrying the registry's blocked label on every repo, so nobody merges it
  before the live step.
- **Blocker isolation.** A blocked ticket halts only its own slot; the rest of the pool
  keeps running and the freed slot takes the next ticket.
- **Preflight**, before the first slot is created: **auth-check** passes, `<data>` is
  writable, the current folder is inside a git repository (workers get a throwaway worktree of
  it; when it is not, stop and tell the user to start Claude Code inside one of the registry's
  clones), and `git -C <one primary clone> fetch origin --prune` succeeds (network,
  credentials, a writable Git directory). When a check fails, stop before touching the board
  and tell the user what failed.
- **One run per board and login at a time.** `ticket_state.py` takes an exclusive lock around
  each write, so a second run waits for it rather than corrupting the record, but two runs
  would still queue the same Ready tickets until a worker moves its card out of Ready. Do not
  start a second run while workers from the first are still going: step 2 would treat their
  slots as unfinished and dispatch them again.
- **Orchestrate; never implement.** You never edit a ticket's code. Workers return a paragraph
  and one `RESULT` line; the run record holds the detail, so do not ask for logs.

## The run record

`<scripts>/ticket_state.py` is the only writer of the run record (workers never touch it):
`init`, `show`, `set-project`, `next-slot`, `begin`, `finish`, `skip`, `clear-skipped`,
`forget`. Its header documents each. A slot's JSON for `begin`:

```json
{
  "slot_id": "slot-1", "ticket_number": 182, "ticket_repo": "shop-app",
  "repos": ["shop-app"], "item_ref": "<handle or null>",
  "resolved_tier": "workhorse", "resolved_model": "sonnet", "resolved_effort": null,
  "started_at": "<ISO 8601>"
}
```

A worker's `RESULT` line goes to `finish --json` as it is (it already carries `slot_id` and
`status`). `active` holds slots that have started and not returned, `completed` holds
`review_opened` tickets with their review links, `blocked` holds every other finished status,
`skipped` is a record of what was not dispatched and why, re-evaluated on every run.

## Phase 1: capture the board

At the start of every run, so a renamed lane or an edited registry takes effect:

1. **current-user** gives the login this run works for. If it cannot be read, halt: "Cannot
   tell who is signed in to the tracker CLI." If `registry.py show` has a non-empty
   `works_for` and it differs from that login (compared case-insensitively), halt: "Signed in
   to the tracker CLI as <login>, but this registry works only for <works_for>. Switch
   accounts (`gh auth switch` or `glab auth login`) and run again."
2. **capture-board** with the registry's board, lanes and priorities gives `tracker_ids`,
   `missing_lanes`, `missing_priorities`, `has_priority` and, on GitHub, `priority_mode`
   (also stored in `tracker_ids`). Without priority support the run
   is fine unless `--priority` was passed; then halt: "Priority filter requested but board
   <board key> has no priority support."
3. From `registry.py show`, take `lanes`, `priorities`, `labels` and `model_labels`. The ready
   lane must not be in `missing_lanes`, or halt and print the raw output of **capture-board**.
   Any other missing lane: warn, and workers will skip that move.
4. Build `repo_map` from the registry, or from `--repo` flags when passed:
   `{ "<name>": { "clone": "<abs path>", "remote": "<Remote>", "brief": "<abs path>" } }`.
5. `ticket_state.py init`, then `set-project --json` with `tracker`, `host`, `board` (the
   resolved board identity), `board_key`, `assignee` (the login), `tracker_ids`, `repo_map`,
   `lanes`, `priorities`, `labels`, `model_labels` and `captured_at`. It refuses (exit 3) when
   the record belongs to a different board or login: halt and say so.

## Orchestration

### 1. Parse arguments

Apply the defaults above. On `--clear-skipped`, run `ticket_state.py clear-skipped`.

### 2. Resume unfinished slots

A non-empty `active` list in the record is a run that did not finish cleanly. Treat those
slots as the first workers of the pool and dispatch each again with the same `slot_id`, after
resolving its model again (step 4). The worker finds its branch on the remote and continues
from what was pushed; work that never reached the remote is redone. This first batch may exceed
`--max-parallel`; log a warning.

### 3. Fetch and filter the queue

Run **list-items** on the ready lane. Each item carries `item_ref`, `number`, `repo`, `type`,
`title`, `lane`, `priority`, `labels` and `assignees`. Keep items whose `lane` equals the
ready lane's value, then drop:

- `type != "issue"`: `skip` with `reason="not an issue: a person merges reviews"`.
  Handed a pull request or merge request, a worker would open a second branch for a change
  that already has one.
- a null `number`: `skip` with `reason="null content number"`.

Then split what is left by assignee, with logins compared case-insensitively. An item whose
`assignees` include the signed-in login stays. An item with no assignees adds one to the
**unassigned** count; an item assigned only to other people adds one to the **assigned to
others** count. Both are left exactly as they are: not dispatched, not recorded, and nothing
written to the ticket. Keep the two counts for the dry run and the report. Then take out the
**held** tickets: any remaining item whose `labels` include the blocked label is somebody's
open hold (a dependency, a decision, a live action or a failure; see
`ticket-labels.md`). Never dispatch it, never touch it.
Count it as held, keeping its number and `repo` for the report. Then drop:

- anything already in `completed`, `blocked` or `active`, matched on the pair
  `(ticket_number, ticket_repo)` and never on the number alone: issue numbers are per repo, so
  two repos routinely reuse one number. `ticket_repo` here is the last part of the item's
  `repo`.
- the run-solo label: `skip` with `reason="run:solo label: human-in-loop required"`.
- neither run label: `skip` with `reason="no run label: ticket has not been groomed"`.
- with `--priority`, any item whose `priority` is not the registry value of a requested role:
  `skip` with `reason="priority <X> not in filter"`.

### 4. Resolve repos and the model

**Repos** follow `registry-rules.md` ("Resolving a
ticket to its repo"): parent repo, then `repo:<name>`, then `project:<name>`, then a body
keyword scan; no match skips with `reason="no repo could be inferred"`, never a guess. The
repo the issue lives in is the owning repo; a ticket may resolve to several.

**Model.** Run the resolver as in "Labels a ticket must carry". Keep its `tier`, `model` and
`effort` as `resolved_tier`, `resolved_model` and `resolved_effort`. A slot resumed from an
earlier run is resolved again from the labels the ticket carries now. Any non-zero exit: `skip`
with the resolver's error as the reason; the ticket is not enqueued. Show any problem the
resolver prints on that ticket's dry-run and report line.

### 5. Sort, then cap

Sort by priority in the rank order of the registry's Priority table (P0 first by default),
then unset, stable within a priority, then keep the first `--limit`.

### 6. Dry run

With `--dry-run`, print the queue, the skipped list and the existing `blocked` list, then
exit. The only side effects are Phase 1 capture and `--clear-skipped`. The "In review" lines
come from the `completed` entries that carry `review_refs`, each checked with **review-state**
on its first `review_refs` entry; list only those still `open`, with their links. A review
that merged or closed drops out of the line.

```text
Ready queue: board <board key> for <login> (max-parallel=<M>, limit=<L>, to-process=<K>)
  #182 "title" repos=[<repo>] owning=<repo> workhorse sonnet P1
Left alone: <A> Ready tickets assigned to others, <U> unassigned
Held (carry the blocked label, not dispatched): <H>
  #71 <repo>: Blocked: dependency
In review (opened by earlier runs, still open): <R>
  #120 <repo>: <review URL>
Not dispatched:
  #60 "title": run:solo label: human-in-loop required
  #64 "title": no run label: ticket has not been groomed
```

### 7. Dispatch loop (a rolling pool)

Keep `--max-parallel` workers running until the queue is empty. Never wait for the rest of the
pool before starting the next ticket: a worker that returns frees a slot, and the next ticket
takes it at once. The pool starts full, so a queue at least as long as `--max-parallel`
starts that many workers together.

Keep your own count of **running** workers: those you dispatched in this run that have not
returned. The pool size is measured against that count, not against `active`, because a slot
whose worker ended without a `RESULT` stays in `active` with nothing running.

**7a. Fill the pool.** Take tickets from the front of the queue until the running count
reaches `--max-parallel`. Slots resumed in step 2 come first and the pool is topped up behind
them. For each ticket get `ticket_state.py next-slot` (one id at a time, calling `begin` right
after each so the next call sees it) and `begin` the slot with its JSON. A `begin` refusal
(exit 3) means the ticket is already tracked: skip it.

**7b. Dispatch.** Build one dispatch message per slot just begun or resumed as the JSON in section 1 of the
worker's agent file, `agents/ticket-worker.md`: `mode`
`dispatched`, the slot, the ticket and its repos, `item_ref`, `assignee`, `project` (from
`set-project`: `tracker`, `host`, `board`, `tracker_ids`, `lanes`, `priorities`, `labels`,
`model_labels`), `repo_map`, `worktree_root`, `files.adapter`, `files.labels`,
`files.ticket_template` (the plugin's `skills/write-ticket/assets/ticket-template.md`) and
`files.check_ticket` (`<scripts>/check_ticket.py`) as absolute paths, `model` (the resolved
model), `validate_plan_first: true` and `context_files` (the owning repo's brief, or the
`--context` files).

Then, in one message, make one Agent call per slot just begun or resumed: `subagent_type` `tickets:ticket-worker`,
`model` set to the slot's resolved model, `effort` set to the slot's resolved effort when it
is not null (this needs Claude Code v2.1.292 or later; on an older version leave it out and
say so in the report), `run_in_background: true` so each result arrives on its own the moment
its worker finishes, and the dispatch message as the prompt. Do not pass `isolation`: the agent
file sets it. Do not poll the workers; their completion notices wake you. After dispatching,
end your turn only to wait for those notices, and print nothing from step 8 until every
dispatched worker has returned: ending the run earlier abandons the workers still going.

- **Concurrent limit.** Claude Code refuses a spawn beyond its concurrent-subagent limit
  (20 by default) with `Concurrent subagent limit reached`. Do not retry in a loop. The slot
  you had begun for that spawn has no worker: run `finish` on it with
  `status=blocked_spawn_failed` and the error text, lower the pool size to what is running,
  and say so in the report.
- **A spawn error** (for example the agent type is not available because the plugin is not
  enabled) puts that slot in `blocked` through `finish` with `status=blocked_spawn_failed` and
  the error text. Never retry it in a loop.

**7c. Reap and refill.** Each time a worker returns, handle that one slot straight away; do
not wait for the others. The worker's last line is `RESULT {...}`:

- `status` starts with `blocked_`, or equals `needs_decision` or `needs_manual_action`: run
  `finish` with the RESULT JSON. Leave its worktrees (the branch and reviews may still need
  them). Print the reason and paths. `needs_manual_action` lands in `blocked` like the others,
  told apart by its `status` and by `manual_action_refs` (review URLs). A `blocked_not_assigned`
  slot means the ticket was reassigned after the queue was built: it is reported, nothing on
  the ticket was touched, and it will not be dispatched again until it is assigned back.
- `status == "review_opened"`: the worker built and tested the ticket and opened a review;
  this is successful work. Run `finish` with the RESULT JSON. The branch is on the
  remote, so nothing is lost. The issue stays open until the review merges. Any
  `follow_up_refs` ride along in the record; the worker already filed those tickets.
- No `RESULT` line, or a status that is not one of those: the worker ended without finishing
  (a turn limit or a crash). Leave the slot in `active` so the next run resumes it, log a
  warning with the worker's last paragraph, and start no further tickets this run (a halt);
  keep reaping the workers still running.

After reaping, go back to 7a so the freed slot takes the next ticket.

**7d.** The loop ends when no worker is still running and either the queue is empty or a halt
stopped new tickets. Slots a halt left in `active` go in the report as "Unfinished".

### 8. Completion

```text
=== work-tickets complete: board <board key> for <login> ===
In review: <R>
  #190 <repo>: <review URL> (slot-2, workhorse sonnet, merging closes the issue)
Follow-ups: <F>
  #201 <repo>: <title> (from #190; a `not_filed` item is listed with its error)
Blocked: <M>
  #50 <repo>: blocked_push_rejected: non-fast-forward (worktree: ...)
  #189 <repo>: needs_manual_action: create the product for plan B and set PRICE_ID_B
    in the hosting env vars. Review https://... (worktree: ...)
Not dispatched: <K>
  #60 "title": run:solo label: human-in-loop required
Unfinished (resume with the next run): <L>
Left alone: <A> Ready tickets assigned to others, <U> unassigned
Held (carry the blocked label, not dispatched): <H>
  #71 <repo>: Blocked: dependency
```

An "In review" line needs nothing from anyone but its reviewer: the ticket is built and tested,
and stays open until its review merges. A "Follow-ups" line comes from the `follow_up_refs`
of `completed` and `blocked` entries: a new backlog ticket (or a comment on an
existing one) for something the worker left undone, declined in review or noticed along the
way, assigned to the same person and waiting for grooming. A `needs_manual_action` line's
reason names the live action and the review links from `manual_action_refs`, which tells the
user at a glance which Blocked items are a bug to fix and which are a click to make. Follow the block with one plain
sentence on what needs the user: the held tickets and the blocked tickets of this run, each
with the kind of its most recent `Blocked:` comment (**read-issue**; a run's own `blocked_*` is
a `failure`, `needs_decision` a `decision`, `needs_manual_action` a `live action`, and a
blocked label with no such comment is "no Blocked comment"), the manual actions with their
links, which reviews are open to merge, and that the "left alone" tickets are not this
person's to work (the unassigned ones need an assignee before `work-tickets` will pick them
up).

## Notes

- **Full restart for one board and login:** delete its file under `<data>/state/`, then
  `git worktree prune` in each registry clone and remove
  `<data>/worktrees/<board key>-<login>/`.
- **Retry** a completed or blocked ticket with `ticket_state.py forget --number N --repo R`.
  The orchestrator never retries a blocker by itself.
- `skipped` persists across runs; `--clear-skipped` empties it.
