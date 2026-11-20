# Board watcher

`scripts/watch_board.py` is the one poller `work-tickets` acts on (orchestrator, "One
poller"). It reads the board every tick and prints one line per new event. It only reads the
tracker: it never moves a card, labels an issue, comments or merges a review. Any watcher you
bring instead must print the same lines.

## Run it

```bash
python3 <scripts>/watch_board.py --data-dir <data> [--interval SECONDS] [--once]
```

`<scripts>` is the plugin's `scripts` folder and `<data>` its data folder
(`${CLAUDE_PLUGIN_DATA}`, which holds `registry.md`). The registry gives the tracker, the
board, the `ready` lane, the blocked label and the repos. It watches the Ready tickets in those
repos, and the open reviews there opened by the login the tracker CLI is signed in as (yours,
and the workers', which use the same login); reviews by anyone else are left out. `--interval` is the seconds
between ticks: 60 by default, at least 10, since every worker and session on the machine shares
the tracker's rate limit. `--once` runs one tick and exits, for a scheduler. Start it in its own
terminal, or as a background command whose output the session reads; stop it with Ctrl-C.

At start it reads the signed-in login over REST. Per tick it makes, on GitHub, one GraphQL query
(the Ready lane and every repo's open pull requests) and a REST read for each pull request that
left the open list. On GitLab it makes REST reads, every page (the Ready label's issues, each
repo's open merge requests by the login, each merge request that left the list), and with
`Lanes: status` one GraphQL query for the Ready lane in place of the issue read. A GraphQL list
reads its first 100 entries and says so on stderr when there are more.

## The event lines

Each event is one line on stdout: the event name, a space, then a one-line JSON object.

```text
NEW_READY {"repo": "acme/shop-app", "number": 12, "title": "Reject emails with no domain", "url": "https://github.com/acme/shop-app/issues/12", "author": "acme-pm"}
```

Every event carries the same five fields:

| Field | Value |
| --- | --- |
| `repo` | The ticket's or review's repo in Remote form (`owner/repo`, or the GitLab project path) |
| `number` | The issue or review number (the GitLab `iid`) |
| `title` | Its title |
| `url` | Its web page |
| `author` | The login that opened it, or `null` for an account the tracker no longer has |

| Event | Item | Fires when |
| --- | --- | --- |
| `NEW_READY` | issue | An open issue in a registry repo is in the registry's `ready` lane |
| `CONFLICT` | review | An open review conflicts with its target branch (GitHub `mergeable: CONFLICTING`; GitLab `has_conflicts` or `detailed_merge_status: conflict`) |
| `QUEUE_READY` | review | An open review can be merged or queued now (GitHub `mergeStateStatus` `CLEAN` or `HAS_HOOKS`; GitLab `detailed_merge_status: mergeable`). A draft, a review carrying the registry's blocked label, a review with checks running or failing, or one missing an approval is not ready |
| `MERGED` | review | A review seen open on an earlier tick has merged |

`NEW_READY`, `CONFLICT` and `QUEUE_READY` fire once when their condition starts. They fire
again only after it stops and starts again: a ticket that leaves Ready and comes back, or a
review whose conflict was fixed and conflicts again. While the tracker recomputes a review's
merge state (GitHub `UNKNOWN`; GitLab `checking`, `unchecked`, `preparing`, `approvals_syncing`),
or the review is still open but missing from the list, it keeps what it held, so the recomputed
answer does not fire again. `MERGED` fires once per review. A review closed without merging, or
deleted, fires nothing.

## Memory and failures

What has fired is kept in `<data>/state/board-watcher-<board>.json`. A restart reads it, so it
prints nothing for events already printed; delete the file and the next tick prints every
current event once. The first tick of a fresh watcher prints every event that holds now. A line
is printed before the memory is saved, so a crash between the two prints that event again on
restart rather than losing it.

| Exit | Meaning |
| --- | --- |
| 0 | Stopped: after one tick with `--once`, or by Ctrl-C |
| 1 | The tick failed, with `--once` (a running watcher prints the error on stderr and tries again next tick) |
| 2 | Bad input, or a memory file it cannot read |
| 3 | The registry is missing or incomplete; the JSON on stderr names what to fill in |
| 4 | `gh` or `glab` is not signed in to the registry's host at start, or a tick's call was refused with a 401; stderr names the login command. Any other failed tick (the network, a rate limit, a server error) is printed on stderr and retried |
