# Ticket registry

This is your team's copy of the ticket registry. The ticket skills created it from the
plugin's `registry.example.md` the first time you ran one, and they read it on every run.
The plugin keeps your copy outside its install folder, so a plugin update never
overwrites it.

Fill in the rows below for your tracker. Every value is exact and case-sensitive: a lane or a priority has to match the name the tracker shows. The skills
read only the tables and the `Key: value` lines; the prose is for you.

**A repo missing from the Repos table is invisible.** Its tickets are skipped with the
reason "no repo could be inferred" and named in the run summary. That is the intended
failure: loud, and never a guess.

**The person running a command is whoever is signed in to the tracker CLI on this
machine.** `work-tickets` and `ticket-worker` touch only tickets assigned to that
person.

## Tracker

- Tracker: `github`
- Host: `github.com`

`Tracker` is `github` or `gitlab`. `Host` is `github.com` or `gitlab.com`, or the host of
a GitHub Enterprise or self-managed GitLab server.

## Board

Fill in the subsection for your tracker and leave the other as it is.

### GitHub

A GitHub Projects (v2) board. The owner is a user or organization login.

- Owner: `your-github-login`
- Number: `1`
- Name: Engineering

### GitLab

An issue board, which is a set of label lists.

- Scope: `group`
- Path: `your-group`
- Board: `Development`

`Scope` is `group` or `project`. `Path` is the group or project path the board belongs
to. `Board` is the board's name or its numeric id.

## Lanes

Each lane as the tracker shows it: on GitHub a Status option name, on GitLab a label,
usually scoped (`status::ready`). A lane whose value is missing from the board is skipped
with a warning when a ticket moves, and a missing `ready` lane stops a run.

The `review` lane is optional: delete its row if the board has no such lane. A worker
that opens a review (every change lands by one) then leaves the card in `in_progress`.
A worker never moves a card to `done`: merging closes the issue and `daily-grooming`
moves the card. Every other lane is required.

| Role | GitHub (Status option) | GitLab (label) | Meaning |
| --- | --- | --- | --- |
| backlog | `Backlog` | `status::backlog` | Filed, not yet queued; where `write-ticket` files by default |
| ready | `Ready` | `status::ready` | Groomed and queued; the only lane `work-tickets` works |
| in_progress | `In progress` | `status::in-progress` | A worker has started |
| blocked | `Blocked` | `status::blocked` | Held; the issue's latest `Blocked:` comment says on what |
| review | `In review` | `status::in-review` | Optional. Work is built and a review is open; merging it closes the issue |
| done | `Done` | `status::done` | Shipped and closed |

## Priority

Each priority as the tracker shows it: on GitHub a Priority option name, on GitLab a
label. A GitHub board with no Priority field, or one with no options, carries priority
as a label instead: the GitHub value below is then the label's name (`P1`), and the
skills read and set that label. Row order is rank, highest first. `--priority P1` names
a role.

| Role | GitHub (Priority option) | GitLab (label) | Meaning |
| --- | --- | --- | --- |
| P0 | `P0` | `priority::0` | Active blocker; nothing ships until it is resolved |
| P1 | `P1` | `priority::1` | On the launch path or blocking infrastructure |
| P2 | `P2` | `priority::2` | Important; same release or shortly after |
| P3 | `P3` | `priority::3` | Nice to have, post-MVP, or deferred |

## Labels

| Role | Label | Color | Description |
| --- | --- | --- | --- |
| blocked | `blocked` | `b60205` | Held: a comment says what it is waiting for |
| run_worker | `run:worker` | `0e8a16` | A worker can finish this end to end |
| run_solo | `run:solo` | `fbca04` | Nothing to build; a person does the whole ticket |

Color and description are used only when a repo lacks the label and a skill creates it.
The name is what the skills match. Labels used without a row here: `effort:<level>`
(optional), `repo:<name>`, `project:<name>`, and `bug` (a worker's commit then says
`Fixes`).

## Model labels

The label that picks a ticket's worker model, one per tier. `work-tickets` reads
whichever label here maps to a tier, and `write-ticket` writes the mapped label. The
tiers run on Claude Haiku (`fast`), Sonnet (`workhorse`) and Opus (`frontier`).

| Tier | Label | Color |
| --- | --- | --- |
| fast | `model:haiku` | `ededed` |
| workhorse | `model:sonnet` | `ededed` |
| frontier | `model:opus` | `ededed` |

The labels `model:fast`, `model:workhorse`, `model:frontier` and the dated
`model:claude-haiku-*`, `model:claude-sonnet-*`, `model:claude-opus-*` forms resolve to
the same three tiers when a ticket carries one the table does not list.

## Repos

| Name | Remote | Local clone | Product brief | Focus |
| --- | --- | --- | --- | --- |
| `my-app` | `your-github-login/my-app` | `~/code/my-app` | `~/code/my-app/README.md` | active |

- **Remote** is `owner/repo` on GitHub and the project path
  (`group/subgroup/project`) on GitLab.
- **Local clone** is the primary clone. Workers never edit, check out or commit in it;
  they work in worktrees made from it.
- **Product brief** is the file a worker reads as the source of truth when it checks a
  ticket's plan. Repos that are components of one product may point at the same brief.
- **Focus** is `active`, `parked` or `unclassified`, the team's ruling on where
  attention goes. The skills read the other four columns and leave Focus to you.

Add a repo here before its tickets reach the board. Deadlines, release dates and other
facts that move are read at run time from the repos and their issues.
