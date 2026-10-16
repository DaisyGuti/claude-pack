---
name: write-ticket
description: Files a bug, idea or request as a ticket on the team's GitHub or GitLab tracker, in the shape the ticket workers need, or rewrites an existing ticket to that shape. Checks the premise against the real repo first (already built, superseded, already ticketed), then files it with priority, model, run and board-lane assignments. Use for "file a ticket", "write this up as an issue", "turn this note into a proper ticket", "rewrite ticket 42", even when the user does not say tracker or labels.
argument-hint: "[--repo NAME] [--ticket N] [--ready] [--assignee LOGIN|me] [--dry-run] <what you want, in your own words>"
disable-model-invocation: true
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/scripts/registry.py *) Bash(${CLAUDE_PLUGIN_ROOT}/scripts/resolve_model.py *) Bash(${CLAUDE_PLUGIN_ROOT}/scripts/check_ticket.py *)
---

# Write ticket

`work-tickets` and `ticket-worker` only work tickets written a particular way. This skill
writes them that way, from an idea or from a rough ticket. The words after the flags are the
description. Infer everything else, make reasonable assumptions instead of asking, and say
which ones you made in the report.

The request: $ARGUMENTS

```text
/tickets:write-ticket <what you want, in your own words>
/tickets:write-ticket --repo my-app <...>        # skip repo inference
/tickets:write-ticket --ticket 42 --repo my-app  # rewrite an existing ticket in place
/tickets:write-ticket --ready <...>              # file into the ready lane instead of backlog
/tickets:write-ticket --assignee me <...>        # assign it: a login, or "me" for the signed-in user
/tickets:write-ticket --dry-run <...>            # show the ticket and its labels, create nothing
```

Paths used below (read them as `<scripts>` and `<data>`):

- Scripts: `${CLAUDE_PLUGIN_ROOT}/scripts`
- Data (the team's registry): `${CLAUDE_PLUGIN_DATA}`

## 0. Set up

1. Run `<scripts>/registry.py ensure --data-dir <data>`. On the first run it creates the team's
   registry and exits 3; on an unfilled one it exits 4. Follow
   [registry-rules.md](${CLAUDE_PLUGIN_ROOT}/references/registry-rules.md) ("Where the registry
   lives"): show what it printed and stop. Do not guess registry values.
2. Run `<scripts>/registry.py show --data-dir <data>` for the tracker, board, lanes,
   priorities, labels, model labels and repos. No default lives in this skill. If a role this
   skill needs is missing (the backlog lane, say), stop and name the row to add.
3. Read the one tracker adapter for the registry's tracker, in full, once:
   [github.md](${CLAUDE_PLUGIN_ROOT}/references/trackers/github.md) or
   [gitlab.md](${CLAUDE_PLUGIN_ROOT}/references/trackers/gitlab.md). Every tracker action below
   is a named operation shown in bold; run each as the adapter writes it.
4. Read [ticket-labels.md](${CLAUDE_PLUGIN_ROOT}/references/ticket-labels.md) for the judgment
   behind each label, and
   [model-selection.md](${CLAUDE_PLUGIN_ROOT}/references/model-selection.md) for the tiers.

## 1. Resolve the repo

`--repo`, or infer it from the description: a repo name from the registry's Repos table, a
file path, a product name, a symbol you can find with one search. **If it is not exactly one
repo, ask.** A ticket in the wrong repo aims the worker's closing keyword at the wrong tracker.
Read that repo's product brief from the registry; you need its audience.

## 2. Prove the premise before writing

Check in the repo's local clone with read-only commands, and run what proves a claim:

1. **Already built?** Search for the symbol, flag, route or config key; run the test file if
   there is one.
2. **Superseded?** Read the repo's `CLAUDE.md`, README and decision records. A ticket against
   a deleted subsystem, a paused platform or a reversed decision is dead on filing.
3. **Already ticketed?** **search-issues** on the keywords, and **list-items** for board items
   on the same repo.
4. **Window passed?** A ticket tied to a date, campaign or season behind us is a decision about
   whether to bother: say so and file nothing.

**If the premise fails, stop and say so**, with the evidence: "this is already built, here is
the test that proves it" is the most valuable result this skill has.

## 3. Write it

Fill [ticket-template.md](${CLAUDE_SKILL_DIR}/assets/ticket-template.md), every section in
order, into a temporary file. Sections 1 to 3 and 5 of the Agent Instructions are boilerplate:
copy them exactly. In section 4's first bullet use the audience from the repo's brief.

- Write `None` under Dependencies rather than dropping the heading. A dependency goes on a
  `Depends on:` line, since the workers' unblock step matches `Depends on:` and `Blocked by:`.
- Omit Out of scope only when there is genuinely nothing a reader would include.
- **Never invent a concrete detail**: a price, a filename, an error string, a date, a metric, a
  version. Every specific is one you read. For a fact you do not have, write
  `- [ ] TBD: <the question>` and say so in the report.
- Split the ticket when the acceptance list runs past about seven bullets or the work spans
  more than two repos.

Then run `<scripts>/check_ticket.py <the file>`. It prints the problems (a placeholder left in,
edited boilerplate, a missing `Depends on:` line, too many acceptance bullets) and exits 1 when
there are any. Fix them and run it again until it exits 0.

## 4. Assign the labels, priority and lane

- **Priority:** one role from the registry's Priority table, judged by its Meaning column.
- **Run label:** exactly one. The run-worker label when there is code or config a worker can
  build and prove, even if the last step is a live action no worker can take; the run-solo
  label only when there is nothing to build at all.
- **Model label:** the tier by difficulty, never urgency, `workhorse` when in doubt, written as
  the label the registry's Model labels table maps that tier to. Name the model the tier runs
  on with `<scripts>/resolve_model.py --tier <tier>` in the report.
- **Other labels:** `project:<repo>`, and the repo's existing area labels (`web`, `bug`, ...)
  from **list-labels**. Never invent an area label.
- **Lane:** the backlog lane, or the ready lane with `--ready`.
- **Assignee:** only with `--assignee`; `me` is **current-user**. Otherwise leave the ticket
  unassigned.
- **Blocked:** when a `Depends on:` issue is still open (**issue-state**), the ticket gets the
  registry's blocked label and a `Blocked: dependency` comment naming each open dependency
  (shape in ticket-labels.md). It keeps the lane it was filed in. `daily-grooming` frees it
  when the last dependency closes.

## 5. File it

`--dry-run` prints the ticket, its labels, lane and assignee and stops; read-only operations
are fine, nothing is created. Filing is this skill's whole job, and the person who typed the
command has asked for it, so file without a further confirmation.

1. **ensure-label** for each label that may be missing (run, model, `project:<repo>`, blocked),
   using the registry's color and description; `project:` labels get color `ededed` and the
   description "Product: <repo>". Area labels are never created.
2. **create-issue** with the title, body file and labels (this also adds it to the board).
3. **set-priority**, then **set-lane**. When the ticket is blocked, **comment** with the
   `Blocked: dependency` comment.
4. **assign** when `--assignee` was given.

`--ticket N`: run **read-issue** first and keep the old body. Stop and say so if the issue is
closed or its lane is in progress or done (find the lane with **list-items**). Otherwise
**edit-issue** with the new body, **remove-label** any run or model label that no longer
applies, add the new ones as in step 1, run **add-to-board** if it is not on the board, then
**set-priority** and **set-lane**, and the blocked label and comment if a dependency is still
open and the issue does not already carry both. Existing assignees stay unless `--assignee` was
given.

Finish every step above before you report. If a write fails, say which one and what is left
undone; never report a ticket as filed that is missing its labels, priority or lane. Delete the
temporary body file when you are done.

## 6. Report

In plain language, outcome first. If step 2 stopped the work, lead with that finding and its
evidence (already built, already ticketed, superseded, window passed). Otherwise lead with the
URL and title, then each assignment with a clause of reasoning, the assumptions you made, and
any `TBD:` bullets. If step 2 found something short of a stop, such as a related ticket, add
it. For `--ticket`, say what the old body held so nothing is lost silently. When the ticket is
unassigned, say that `/tickets:work-tickets` will not pick it up until someone is assigned.
