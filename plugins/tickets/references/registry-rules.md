# Registry rules: board arguments, repos and briefs

The registry holds the team's facts: tracker, board, lanes, priorities, labels and repos
(see the plugin's `registry.example.md`). This file holds the rules for reading it, so a
plugin update improves them without touching the team's copy. `<scripts>` and `<data>` are
the two paths printed at the top of the skill that sent you here.

## Contents

- Where the registry lives
- Reading it
- Resolving a project board argument
- Resolving a ticket to its repo
- Resolving a ticket's product brief

## Where the registry lives

`<data>/registry.md`, in the plugin's data folder, which survives plugin updates. The first
run of any ticket skill creates it from `registry.example.md` and stops so the user can fill
it in. Run this as step 0 of every skill:

```bash
<scripts>/registry.py ensure --data-dir <data>
```

- Exit 0: the registry is ready; continue.
- Exit 3: it was just created. Tell the user the path, list the sections to fill in (Tracker,
  Board, Lanes, Priority, Labels, Model labels, Repos) and stop. Do not guess values for
  them.
- Exit 4: the printed `problems` say what is missing or still holds an example value. Show
  them and stop.

## Reading it

```bash
<scripts>/registry.py show --data-dir <data>
```

prints the registry as JSON: `tracker`, `host`, `board`, `lanes` (role to the value for the
registry's tracker), `lane_meaning`, `priorities` (in rank order, each with `role`, `value`,
`meaning`), `labels` (role to `name`, `color`, `description`), `model_labels` (tier to
`label`, `color`) and `repos` (each with `name`, `remote`, `clone`, `brief`, `focus`). Use
those values everywhere; never keep a second copy of a lane, label or repo in a skill, a
ticket or a comment. Then read the one tracker adapter,
`references/trackers/<tracker>.md`, in full.

## Resolving a project board argument

Every ticket skill takes the default board from the registry. It also accepts `--project N`
and `--owner OWNER` (on GitHub the board's number and owner; on GitLab `--owner` is the
group or project path and `--project` the board's numeric id), or a pasted board URL, which
narrows the run to that board:

```bash
<scripts>/registry.py board-url "<url>" --data-dir <data>
```

It prints `{kind, owner, number}` for a GitHub project or `{kind, scope, path, board_id}` for
a GitLab board, and treats the result exactly as if `--project` and `--owner` had been typed.
Recognized shapes: `https://github.com/users/<owner>/projects/<N>` and
`https://github.com/orgs/<owner>/projects/<N>` (a `/views/<V>` suffix is ignored),
`https://<host>/groups/<group path>/-/boards/<id>` and `https://<host>/<project path>/-/boards/<id>`
(a query string is ignored). Exit 5 means the URL's host differs from the registry's Host:
stop and say so. When the resolved board equals the registry's default board, say so in the
output so the run does not look narrower than it is.

## Resolving a ticket to its repo

Use these rules in order; the first match wins.

1. **Parent repo.** The board item's `repo` (the Remote form; the name is the last part of
   the path). It is the repo the issue lives in and is correct for nearly every ticket.
2. **Explicit label.** A `repo:<name>` label naming a Repos row.
3. **Project label.** A `project:<name>` label naming a Repos row.
4. **Body keyword scan.** A case-insensitive search of the ticket body for each Repos name;
   every hit is a target repo.
5. **No match.** Skip the ticket with the reason "no repo could be inferred" and surface it
   in the summary. A guess would aim the closing keyword at the wrong tracker.

A ticket may resolve to several repos. The repo it lives in (rule 1) is the **owning repo**:
labels, plan comments and the auto-close keyword go there.

## Resolving a ticket's product brief

Look up the owning repo in the Repos table and read its Product brief. A board that spans
several products gets each ticket's own repo brief, never one board-wide file: a ticket
planned against another product's brief is worse than one planned against none. An explicit
`--context FILE` still wins, for single-product runs where one brief covers the whole board.
A brief missing on disk is reported and the run continues without it.
