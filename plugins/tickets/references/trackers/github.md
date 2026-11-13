# Tracker adapter: GitHub

The exact commands for each tracker operation when the registry says
`tracker: github`. Procedures name an operation (for example **set-lane**); this file
says how to run it. It uses the GitHub CLI (`gh`) and GitHub Projects (v2). Flags were
checked against `gh` 2.101.0 on 2026-10-08, and the JSON shapes against a live board.

Read this file once, before the first tracker action of a run, and only when the
registry's tracker is `github`. Run each operation exactly as written below; never
improvise a command for one. When the installed `gh` rejects a flag, run
`gh <command> --help`, tell the user which flag changed, and carry on with the equivalent.

## Contents

- Terms used in the commands
- auth-check
- capture-board
- list-items
- read-issue
- issue-state
- search-issues
- current-user
- assign
- comment
- set-lane
- set-priority
- add-label
- remove-label
- ensure-label
- list-labels
- create-issue
- add-to-board
- edit-issue
- close-issue
- verify-closed
- open-review
- list-blocked
- list-open-issues
- list-open-reviews
- review-state
- list-parents
- read-parent
- create-parent
- attach-child
- comment-parent
- read-parent-item
- close-parent

## Terms used in the commands

- `<remote>` is the repo's registry Remote, `owner/repo`. `<n>` is the issue number.
- `<N>` and `<O>` are the board's number and owner from the registry (or the state
  file's `project.board`).
- `tracker_ids` is the object **capture-board** returns. It is stored in the state
  file's `project.tracker_ids` and read only by this file's commands.
- `item_ref` is a board item's node id (`PVTI_...`).
- A **review** is a pull request. A lane value is a Status option name. A priority
  value is a Priority option name on a board in **field mode**, and a label name on a
  board in **label mode** (see **capture-board**). All are compared exactly,
  case-sensitively.
- A host other than github.com: export `GH_HOST=<host>` for the whole run. Every
  command below then talks to that host.
- Long text goes in a file passed with `--body-file`, so quoting never mangles it.

## auth-check

Contract: succeeds only when the CLI is signed in to the registry's host and can read
and write issues and the board; any failure or unparseable output is a failure.

```bash
gh auth status            # add --hostname <host> for a host other than github.com
```

A non-zero exit means not signed in. The token needs the `repo` and `project` scopes, which `gh auth status` prints.

## capture-board

Contract: resolves the board, lane and priority ids from the registry's Board, Lanes
and Priority values. Returns `tracker_ids`, `missing_lanes` (lane roles whose value is
not on the board), `missing_priorities` (priority roles whose value is not on the
board), `priority_mode` (`field` or `label`) and `has_priority` (the board can carry a
priority). The caller decides which missing value halts a run.

```bash
gh project view <N> --owner <O> --format json --jq .id
gh project field-list <N> --owner <O> --format json --limit 100
```

From the first, `project_id` (the board's node id, `PVT_...`). From the second,
the fields named `Status` and `Priority`: each field's `id` and its `options` as a
map of option name to option id. `tracker_ids` is:

```json
{
  "project_id": "PVT_...",
  "status_field_id": "PVTSSF_...", "status_options": { "<option name>": "<id>" },
  "priority_mode": "field",
  "priority_field_id": "PVTSSF_...", "priority_options": { "<option name>": "<id>" }
}
```

`priority_mode` is returned on its own and also stored inside `tracker_ids`, so every
later command reads the mode from the state file. It is `field` when the board has a
Priority field with at least one option:
a priority is that field's option, and a registry priority value that is not a key of
`priority_options` goes in `missing_priorities`. Otherwise (no Priority field, or one
with no options) `priority_mode` is `label`: a priority is a label on the issue named
exactly like the registry's priority value (`P1`), `priority_field_id` is null,
`priority_options` is empty and `missing_priorities` is empty, because **set-priority**
creates a missing label in the issue's repo when it first sets it. `has_priority` is
true in both modes. A registry lane value that is not a key of `status_options` goes in
`missing_lanes`. Print the raw output when the caller halts on a missing value.

## list-items

Contract: every board item, optionally only those in one lane, as
`{item_ref, number, repo, type, title, lane, priority, labels, assignees}`. `repo` is the
Remote form (`owner/repo`). `type` is `issue`, `review` or `other` (a draft item).
`lane` and `priority` are registry values, or null when unset. `assignees` is a list of logins, empty when unassigned. `number` is null for a
draft item. In field mode `priority` is the Priority field's value, null when the field is
empty. In label mode it is the highest-ranked registry priority value the item carries as
a label.

```bash
gh project item-list <N> --owner <O> --format json --limit 1000 --jq '["<every priority value, in rank order>"] as $prios | .items[] | (.labels // []) as $labels | {
  item_ref: .id, number: .content.number, repo: .content.repository,
  type: (if .content.type == "Issue" then "issue" elif .content.type == "PullRequest" then "review" else "other" end),
  title: .title, lane: .status,
  priority: (.priority // ([$prios[] | select(. as $p | any($labels[]; . == $p))] | .[0])),
  labels: $labels, assignees: (.assignees // [])}'
```

The first array depends on `tracker_ids.priority_mode`. In label mode, write the
registry's priority values into it, highest rank first, as JSON strings
(`["P0","P1","P2","P3"]`). In field mode, write `[]`, so labels never stand in for an
empty field: daily-grooming has to see that field as empty to fill it.

Use 1000: the list comes back oldest first, so a lower cap hides the newest items.
Keep only items whose `lane` equals the requested lane value when one was asked for.
Re-read this list to recover an `item_ref`: match on the pair `(number, repo)`.

## read-issue

Contract: `{title, body, labels, assignees, state, comments[{created, body}], created, updated}`
for one issue; `assignees` is a list of logins, empty when unassigned; `state` is `open` or `closed`.

```bash
gh issue view <n> --repo <remote> --json title,body,labels,assignees,state,comments,createdAt,updatedAt --jq '{
  title, body, labels: [.labels[].name], assignees: [.assignees[].login], state: (.state | ascii_downcase),
  comments: [.comments[] | {created: .createdAt, body}], created: .createdAt, updated: .updatedAt}'
```

## issue-state

Contract: `open` or `closed` for each issue in a list of numbers in one repo, with
the close time when closed.

```bash
gh issue view <n> --repo <remote> --json state,closedAt --jq '{state: (.state | ascii_downcase), closed_at: .closedAt}'
```

Run it once per number.

## search-issues

Contract: issues of any state in one repo matching keywords, as
`{number, title, state, url}`, newest first, at most 20.

```bash
gh issue list --repo <remote> --state all --search "<keywords>" --limit 20 \
  --json number,title,state,url --jq '.[] | {number, title, state: (.state | ascii_downcase), url}'
```

To find the model-fit notes workers leave, search `"Model-fit note in:comments"`.

## current-user

Contract: the login of the account the CLI is signed in as, on the registry's host.
Fails when it cannot be read; an empty or unparseable answer is a failure.

```bash
gh api user --jq .login
```

## assign

Contract: adds one login to an issue's assignees, leaving the other assignees alone.

```bash
gh issue edit <n> --repo <remote> --add-assignee "<login>"
```

## comment

Contract: posts text as a new comment on one issue.

```bash
gh issue comment <n> --repo <remote> --body-file <file>      # or -b "<short text>"
```

## set-lane

Contract: moves one issue's board item to the lane named by a lane role. The lane
value comes from the registry's Lanes table for the role. When the value is in
`missing_lanes`, skip the move, log a warning and carry on; never block on it.

```bash
gh project item-edit --project-id <tracker_ids.project_id> --id <item_ref> \
  --field-id <tracker_ids.status_field_id> \
  --single-select-option-id <tracker_ids.status_options[lane value]>
```

`item_ref` comes from the run record or the worker's dispatch message. When it is missing, or the command reports
the item not found, re-resolve it with **list-items** by `(number, repo)`.

A value is also missing when it is not a key of `status_options`.

## set-priority

Contract: sets one issue's priority to the value named by a priority role, leaving it
with exactly that one priority. Same skip rule as **set-lane** for a value in
`missing_priorities`.

The branch follows `tracker_ids.priority_mode`.

Field mode:

```bash
gh project item-edit --project-id <tracker_ids.project_id> --id <item_ref> \
  --field-id <tracker_ids.priority_field_id> \
  --single-select-option-id <tracker_ids.priority_options[priority value]>
```

Label mode: run **ensure-label** for the value (color `ededed`, description
`Priority: <value>`), take the issue's labels from **read-issue**, then add the value and
remove every other registry priority value the issue carries, in one edit:

```bash
gh issue edit <n> --repo <remote> --add-label "<priority value>" \
  --remove-label "<the other priority values the issue carries, comma separated>"
```

Leave out `--remove-label` when the issue carries no other priority value. Confirm with
**read-issue** that the old priority label is gone, the new one is on, and every other
label is untouched.

## add-label

Contract: adds one label that already exists in the repo to one issue.

```bash
gh issue edit <n> --repo <remote> --add-label "<name>"
```

## remove-label

Contract: removes one label from one issue; a label the issue does not carry is not
an error worth stopping for.

```bash
gh issue edit <n> --repo <remote> --remove-label "<name>"
```

## ensure-label

Contract: makes sure a label exists in the repo, creating it with the registry's
color and description when missing. Never changes an existing label.

```bash
gh label list --repo <remote> --search "<name>" --json name --jq '.[].name'
```

The search matches substrings, so compare each returned name to `<name>` exactly. When
none matches:

```bash
gh label create "<name>" --repo <remote> --color "<color without #>" --description "<description>"
```

## list-labels

Contract: every label in the repo as `{name, color, description}`.

```bash
gh label list --repo <remote> --limit 200 --json name,color,description
```

## create-issue

Contract: creates an issue with a title, a body and labels (each label already
ensured), then runs **add-to-board**. Returns `{number, url, item_ref}`.

```bash
gh issue create --repo <remote> --title "<title>" --body-file <file> --label "<a>" --label "<b>"
```

It prints the new issue's URL; the number is the last path segment.

## add-to-board

Contract: puts an existing issue on the board and returns its `item_ref`.

```bash
gh project item-add <N> --owner <O> --url <issue url> --format json --jq .id
```

## edit-issue

Contract: replaces an issue's body, and its title when one is given.

```bash
gh issue edit <n> --repo <remote> --body-file <file> [--title "<title>"]
```

## close-issue

Contract: closes one issue with a closing comment.

```bash
gh issue close <n> --repo <remote> --comment "<comment>"
```

**Closing keywords for a commit message.** The keyword closes the issue when the
commit reaches the default branch.

- Same repo: `Closes #<n>`, or `Fixes #<n>` for a bug.
- Another repo, closing: `Closes <owner>/<repo>#<n>`.
- Another repo, not closing: `Refs <owner>/<repo>#<n>`.

## verify-closed

Contract: confirms an issue is closed, polling up to 5 times, 2 seconds apart. Returns
true on the first `closed`.

```bash
gh issue view <n> --repo <remote> --json state --jq '.state | ascii_downcase'
```

Repeat until it prints `closed` or the fifth try has failed.

## open-review

Contract: opens a review from a pushed branch into `<base>`, the repo's default branch
as the caller resolved it (never assumed to be `main`), with a title, a body and, when
the caller asks for one, one label (already ensured); leave the label argument out
otherwise. Returns the review URL.

```bash
gh pr create --repo <remote> --head <branch> --base <base> --title "<title>" \
  --body-file <file> [--label "<label>"]
```

It prints the pull request URL.

## list-blocked

Contract: open issues in one repo carrying the blocked label, as `{number, body}`, at
most 100.

```bash
gh issue list --repo <remote> --state open --label "<blocked label>" --limit 100 --json number,body
```

## list-open-issues

Contract: every open issue in one repo as `{number, title, body, labels, assignees}`, newest first, at most 1000. `labels` is a list of names and `assignees` a list of logins. An issue missing from this list is closed or beyond the cap, so a caller that means to act on its absence confirms it with **issue-state** first.

```bash
gh issue list --repo <remote> --state open --limit 1000 --json number,title,body,labels,assignees \
  --jq '.[] | {number, title, body, labels: [.labels[].name], assignees: [.assignees[].login]}'
```

## list-open-reviews

Contract: every open review in one repo as `{number, url, closes}`, newest first, at most 1000. `closes` lists the numbers of the issues in the same repo that the review closes when it merges (a closing keyword in its description, or a link made in the web page); it is empty for a review that only mentions an issue.

```bash
gh pr list --repo <remote> --state open --limit 1000 --json number,url,closingIssuesReferences \
  --jq '.[] | {number, url, closes: [.closingIssuesReferences[] | select(.repository.owner.login + "/" + .repository.name == "<remote>") | .number]}'
```

## review-state

Contract: `open`, `merged` or `closed` for one review (a closed review that was not merged reads `closed`). Fails when the number is not a review in that repo.

```bash
gh pr view <n> --repo <remote> --json state --jq '.state | ascii_downcase'
```

## Batch parents

A batch is one parent with child tickets, worked in one branch and one pull request. On
GitHub the parent is an ordinary issue in the same repo and the children are its native
sub-issues. A parent is not a ticket, so it is never on the board. Docs read 2026-11-13:
https://docs.github.com/en/rest/issues/sub-issues,
https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/adding-sub-issues,
and the GraphQL schema by introspection (`__type(name: "Issue")`).

Limits, from the docs: up to 100 sub-issues per parent, up to eight levels of nesting.
The REST page requires the sub-issue to belong to the same repository **owner** as the
parent, so a child may live in another repo of the same owner; it states no same-repo
rule. `parent_ref` is the parent's issue number (as a string). A parent's children
carry their own `repo`, which is the parent's repo for a same-repo batch.

## list-parents

Contract: every open issue in one repo that has sub-issues, with its children, as
`{parent_ref, number, repo, title, url, labels, children: [{number, repo, state}]}`, at
most 100 parents. `parent_ref` is the parent's issue number; `labels` is a list of names;
`state` is `open` or `closed`.

```bash
gh api graphql --paginate -f query='query($endCursor:String){ repository(owner:"<owner>",name:"<repo>"){
  issues(states:OPEN,first:100,after:$endCursor){ pageInfo{hasNextPage endCursor}
    nodes{ number title url repository{nameWithOwner} labels(first:50){nodes{name}}
      subIssuesSummary{total} subIssues(first:100){nodes{number state repository{nameWithOwner}}} } } } }' \
  --jq '.data.repository.issues.nodes[] | select(.subIssuesSummary.total > 0) | {
    parent_ref: (.number | tostring), number, repo: .repository.nameWithOwner, title, url,
    labels: [.labels.nodes[].name],
    children: [.subIssues.nodes[] | {number, repo: .repository.nameWithOwner, state: (.state | ascii_downcase)}]}'
```

`<owner>` and `<repo>` are the two halves of `<remote>`. GraphQL cannot filter issues by
"has sub-issues" (a `has:sub-issues` search qualifier is silently ignored and returns every
issue), so the query pages through every open issue, 100 per call, and keeps those whose
`subIssuesSummary.total` is above zero; `--paginate` follows the cursor. `subIssues(first:100)`
covers the 100-per-parent limit in one page. Keep the first 100 parents printed. Ran on
RedCellPartners/quarterdeck: 367 open issues, 21 parents, for example parent 341 with
`labels: ["project:quarterdeck","P2","req:REQ-30","batch:cui"]` and children
`{"number":177,"repo":"RedCellPartners/quarterdeck","state":"closed"}`. The jq output is one
JSON object per parent, not an array.

## read-parent

Contract: a ticket's parent as `{parent_ref, number, repo, title, url, state}`, or null
when it has none. `state` is `open` or `closed`.

```bash
gh api graphql -f query='{repository(owner:"<owner>",name:"<repo>"){issue(number:<n>){
  parent{number title url state repository{nameWithOwner}}}}}' \
  --jq '.data.repository.issue.parent | if . == null then null else {
    parent_ref: (.number | tostring), number, repo: .repository.nameWithOwner, title, url,
    state: (.state | ascii_downcase)} end'
```

An issue with no parent prints `null`. REST has the same read,
`gh api repos/<owner>/<repo>/issues/<n>/parent`, but it answers HTTP 404 "No parent issue
found" (non-zero exit) when there is none, and returns the full REST issue object (`number`,
`title`, `html_url`, `state`, `id`), so use the GraphQL form. Ran both on
RedCellPartners/quarterdeck: issue 117 gives parent 341 "CUI-ready production", open;
issue 4235 gives `null` (GraphQL, exit 0) and the 404 (REST).

## create-parent

Contract: creates the parent issue with a title, a body and labels (each label already
ensured). It is not added to the board. Returns `{parent_ref, number, url}`.

```bash
gh issue create --repo <remote> --title "<title>" --body-file <file> --label "<a>" --label "<b>"
```

This is **create-issue** without **add-to-board**. It prints the issue's URL; the number is
the last path segment, and `parent_ref` is that number.

UNVERIFIED: not run, because the check was read-only; the command is the one **create-issue**
documents, and nothing in it is specific to a parent.

## attach-child

Contract: makes one issue a sub-issue of a parent, replacing any parent it had.

```bash
gh api repos/<owner>/<repo>/issues/<parent>/sub_issues -X POST \
  -F sub_issue_id=<child id> -F replace_parent=true
```

`<child id>` is the child's numeric database `id`, not its issue number. Get it with:

```bash
gh api repos/<child owner>/<child repo>/issues/<child n> --jq .id
```

`-F` sends the values as an integer and a boolean; `-f` would send strings and fail. The
call answers 201 with the parent issue. A 422 is a validation failure or spam detection; 403,
404 and 410 are permission, missing or gone. Creating or removing sub-issues too fast can hit
secondary rate limits, so attach children one at a time. Limits are in **Batch parents**
above (100 per parent, eight levels, same owner). To detach, `DELETE
repos/<owner>/<repo>/issues/<parent>/sub_issue` with `sub_issue_id`. GraphQL has an
alternative, the `addSubIssue` mutation (`issueId` the parent's node id, `subIssueId` or
`subIssueUrl`, `replaceParent`); it is not needed.

Ran the id lookup on RedCellPartners/quarterdeck: issue 117 has `id` 5836175230 and node id
`I_kwDOT9Bmv88AAAABW9z3fg`. REST list of a parent's children
(`gh api repos/<owner>/<repo>/issues/<parent>/sub_issues`, `per_page` up to 100) returned 7
for parent 341, matching the GraphQL list.

UNVERIFIED: the POST itself was not run (read-only check). The path, body fields and
`replace_parent` come from the REST docs; the `addSubIssue` input fields were confirmed by
schema introspection (`issueId`, `subIssueId`, `subIssueUrl`, `replaceParent`). Verify an
attach with **read-parent** on the child.

## comment-parent

Contract: posts text as a new comment on the parent. On GitHub it is **comment** on the
parent's number.

## read-parent-item

Contract: the parent's title, body, state and comments. On GitHub it is **read-issue** on
the parent's number.

## close-parent

Contract: closes the parent with a closing comment. On GitHub it is **close-issue** on the
parent's number. A pull request body line `Closes #<parent>` closes the parent when the
pull request merges, like any issue (see **close-issue** for the keywords).

UNVERIFIED: not run for a parent. Closing a parent is documented here only as the ordinary
issue close; the docs read do not say that closing a parent changes its sub-issues, so close
each child separately.
