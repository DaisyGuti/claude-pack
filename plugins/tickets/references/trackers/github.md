# Tracker adapter: GitHub

The exact commands for each tracker operation when the registry says
`tracker: github`. Procedures name an operation (for example **set-lane**); this file
says how to run it. It uses the GitHub CLI (`gh`) and GitHub Projects (v2). Flags were
checked against `gh` 2.101.0 on 2026-10-08, and the JSON shapes against a live board.
On 2026-11-24, with `gh` 2.103.0, **capture-board**'s weight field, **add-to-board**,
**set-weight**'s project field path, **read-milestone** and every batch parent write ran for
real on github.com against a throwaway user-owned project and a private repo of the same user.
What that setup could not show is marked `UNVERIFIED:` with the reason.

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
- read-milestone
- set-milestone
- set-weight
- close-issue
- verify-closed
- open-review
- list-blocked
- list-open-issues
- list-open-reviews
- review-state
- merged-reviews
- list-blockers
- add-blocker
- remove-blocker
- Batch parents
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
  "priority_field_id": "PVTSSF_...", "priority_options": { "<option name>": "<id>" },
  "weight_field_id": "PVTF_... or null"
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

`weight_field_id` is the id of the board's number field named `Weight`, or null. The field
list above cannot say which: it reports every field that is not a single select as
`"type": "ProjectV2Field"`, a text field included. Read the data type with a third call:

```bash
gh api graphql -f id=<project_id> -f query='query($id: ID!) { node(id: $id) { ... on ProjectV2 {
  fields(first: 100) { nodes { ... on ProjectV2Field { id name dataType } } } } } }' \
  --jq '{weight_field_id: ([.data.node.fields.nodes[] | select(.name == "Weight" and .dataType == "NUMBER")][0].id)}'
```

It prints `{"weight_field_id":null}` when the board has no such field, or only a `Weight` of
another type. Do not use `field(name: "Weight")`: a name the board lacks fails the call with
`NOT_FOUND` and exit 1. Checked on the throwaway board: it printed null before any `Weight`
field existed, and the `PVTF_...` id once a number field named `Weight` was created. The same
query with a text field's name printed null, so the `dataType` filter leaves text fields out.

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

To find the model-fit notes workers leave, search `"Model-fit note in:comments"`. Checked
2026-11-24: it found an issue by a comment's text, but only some seconds after the comment
was posted, once the search index caught up; asked at once it printed nothing.

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

Label mode: run **ensure-label** for the value (color and description from
ticket-labels.md, "Label colors and descriptions"), take the issue's labels from **read-issue**, then add the value and
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

Checked 2026-11-24: it printed the new item's `PVTI_...` id.

## edit-issue

Contract: replaces an issue's body, and its title when one is given.

```bash
gh issue edit <n> --repo <remote> --body-file <file> [--title "<title>"]
```

## read-milestone

Contract: `{"milestone": {id, title}}` for one issue, or `{"milestone": null}` when it has
none. `id` is the milestone's number. A batch parent in `sub-issues` mode is an issue, so its
milestone is read the same way, with the parent's `number` and `repo`.

```bash
gh issue view <n> --repo <remote> --json milestone \
  --jq '{milestone: (.milestone | if . == null then null else {id: .number, title} end)}'
```

Checked 2026-11-24: an issue with no milestone printed `{"milestone":null}`, and the same issue
in a new milestone printed its number and title.

## set-milestone

Contract: puts one issue in a milestone of its own repo, by title, replacing any milestone it
had. A title the repo does not have fails with `'<title>' not found` and changes nothing.

```bash
gh issue edit <n> --repo <remote> --milestone "<title>"
```

Checked 2026-11-20 with `gh` 2.103.0: set, read back and removed (`--remove-milestone`) on a
real issue, and the not-found error on an unknown title.

## set-weight

Contract: sets one issue's weight to a whole number, replacing any weight it had.

A GitHub issue has no built-in weight. Two fields can carry one, tried in this order:

1. **An issue field.** A number issue field named `Weight`, defined by the repo's owner (an
   organization or a user, in its Settings under "Issue fields"; GitHub docs, "Managing issue
   fields", read 2026-11-24:
   https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/managing-issue-fields).
   It lives on the issue in every repo of that owner, like GitLab's weight. Run the lookup for
   each issue, since repos of one board can have different owners. `<owner>` and `<repo>` are
   the two halves of `<remote>`. Look up the issue and the field in one call:

   ```bash
   gh api graphql -f owner=<owner> -f repo=<repo> -F n=<n> -f query='query($owner: String!, $repo: String!, $n: Int!) {
     repository(owner: $owner, name: $repo) { issue(number: $n) { id }
       issueFields(first: 25) { nodes { ... on IssueFieldNumber { id name } } } } }' \
     --jq '.data.repository | {issue_id: .issue.id, field_id: ([.issueFields.nodes[] | select(.name == "Weight")][0].id)}'
   ```

   An owner has at most 25 issue fields (the same page), so one page holds them all. A host
   whose schema has no `issueFields` (an older GitHub Enterprise Server) fails the lookup with
   a GraphQL error that names `issueFields`; count that one error as no issue field and go to
   the project field. Any other failed lookup is a failure to report. UNVERIFIED: the exact
   error text on such a host (none was available). With a
   `field_id`, set the value and read it back:

   ```bash
   gh api graphql -f issue=<issue_id> -f field=<field_id> -F w=<weight> \
     -f query='mutation($issue: ID!, $field: ID!, $w: Float!) {
     setIssueFieldValue(input: {issueId: $issue, issueFields: [{fieldId: $field, numberValue: $w}]}) {
       issue { issueFieldValues(first: 25) { nodes { ... on IssueFieldNumberValue {
         value field { ... on IssueFieldNumber { id } } } } } } } }' \
     --jq '[.data.setIssueFieldValue.issue.issueFieldValues.nodes[] | select(.field.id == "<field_id>") | .value] == [<weight>]'
   ```

   It succeeds only when it prints `true`. A non-zero exit or `false` is a failure to report
   for that issue; do not also write the project field, so the issue never carries two
   weights. `gh` has no flag for issue fields (`gh issue edit`
   in 2.103.0 has none), so both calls go through `gh api graphql`. The REST form is
   `PUT` or `POST repos/<owner>/<repo>/issues/<n>/issue-field-values`; it takes the field's
   numeric id and `PUT` replaces every field value on the issue, so the GraphQL form is used.
   Checked 2026-11-24: the lookup ran for real on a user-owned repo with no issue fields and
   printed `field_id` null. UNVERIFIED: the mutation against a real field. Defining an issue
   field (`createIssueField`) needs the `user` or `admin:org` scope, which the checking token
   lacked, so the mutation ran only against a field id that does not exist: it accepted the
   input types with the `repo` and `project` scopes and failed with `NOT_FOUND`, exit 1.
2. **A project field.** Without an issue field, the board's number field named `Weight`,
   `tracker_ids.weight_field_id` from **capture-board**:

   ```bash
   gh project item-edit --project-id <tracker_ids.project_id> --id <item_ref> \
     --field-id <tracker_ids.weight_field_id> --number <weight>
   gh api graphql -f id=<item_ref> -f query='query($id: ID!) { node(id: $id) { ... on ProjectV2Item {
     fieldValueByName(name: "Weight") { ... on ProjectV2ItemFieldNumberValue { number } } } } }' \
     --jq '.data.node.fieldValueByName.number == <weight>'
   ```

   It succeeds only when the second command prints `true`. The value lives on the board
   item, so an issue on two boards has a weight on each. Checked 2026-11-24: set 3, then 5,
   each read back, and **list-items**' raw item shows it as `"weight": 5`. A `--number` on a
   text field fails with `Did not receive a text value`, and an unknown `item_ref` fails with
   `Could not resolve to a node`, both exit 1. `--number` also takes a decimal, so pass the
   registry's whole number as written.

With neither field for an issue (its lookup's `field_id` and `weight_field_id` both null),
skip that issue's weight. Say so once for the run, naming both fields so the user can add
one, and keep running the lookup for later issues.

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

## merged-reviews

Contract: the merged reviews in the same repo whose description has a `Refs` line naming one
issue and that merged into the repo's default branch, as `{number, url, merged_at}`, one per
line; nothing when there are none. Such a review leaves the issue open, and its work is on the
default branch: maybe all of it, maybe only a part (a worker writes `Refs` for a change that
finishes part of a ticket), so a person reads it before anything stops waiting on the issue. A
review that only mentions the issue in prose does not count.

```bash
gh repo view <remote> --json defaultBranchRef --jq .defaultBranchRef.name
gh api --paginate "repos/<remote>/issues/<n>/timeline?per_page=100" --jq '.[]
  | select(.event == "cross-referenced" and .source.issue.pull_request.merged_at != null)
  | .source.issue | select(.repository.full_name == "<remote>")
  | select((.body // "") | split("\n") | any(test("^\\W*refs?\\b"; "i") and test("(#|/issues/)<n>(\\D|$)")))
  | {number, url: .html_url, merged_at: .pull_request.merged_at}'
gh pr view <number> --repo <remote> --json baseRefName --jq .baseRefName
```

The first command gives the default branch, once per repo. Run the third once per review the
second prints, and keep the ones whose base is the default branch. A review that mentions the
issue leaves a `cross-referenced` event on its timeline whatever the keyword, a mention in
prose included; the body test keeps the ones with a `Refs` line. Checked 2026-11-25 with `gh`
2.103.0 on a throwaway private repo: an issue, then a pull request with `Refs #<n>` in its body,
squash-merged; the issue stayed open, the second command printed the pull request with its
merge time, and the third printed `main`.

## list-blockers

Contract: for one issue, the issues it is blocked by and the issues it blocks (native issue
dependencies), each as `{ref, state}`, `ref` written `owner/repo#<n>`. A dependency is this
link and nothing else: a `Depends on:` line in a body is not one.

```bash
gh api --paginate "repos/<remote>/issues/<n>/dependencies/blocked_by?per_page=100" \
  --jq '.[] | {ref: ((.repository_url | sub(".*/repos/"; "")) + "#" + (.number | tostring)), state}'
gh api --paginate "repos/<remote>/issues/<n>/dependencies/blocking?per_page=100" \
  --jq '.[] | {ref: ((.repository_url | sub(".*/repos/"; "")) + "#" + (.number | tostring)), state}'
```

The first prints the blockers, the second the issues it blocks. A closed blocker is listed with
`state` `closed`. For a whole repo at once, `scripts/links.py fetch` reads every open issue's
`blockedBy` in one paged GraphQL query (it lists closed blockers too). Checked 2026-11-25 with
`gh` 2.103.0 on a throwaway private repo: both commands, before and after the blocker closed.

## add-blocker

Contract: marks issue `<n>` as blocked by another issue (`<blocker>`, in this repo or another).
Link an issue, never a review: a ticket waiting on a pull request is linked to that pull
request's issue.

```bash
gh api "repos/<blocker remote>/issues/<blocker n>" --jq .id
gh api -X POST "repos/<remote>/issues/<n>/dependencies/blocked_by" -F issue_id=<id>
```

The first command gives the blocker's numeric id (not its number). Checked 2026-11-25 on the
throwaway repo: the link appeared in **list-blockers** on both issues, and `links.py migrate
--apply` added one the same way.

## remove-blocker

Contract: removes the link that marks issue `<n>` as blocked by `<blocker>`.

```bash
gh api "repos/<blocker remote>/issues/<blocker n>" --jq .id
gh api -X DELETE "repos/<remote>/issues/<n>/dependencies/blocked_by/<id>"
```

Checked 2026-11-25 on the throwaway repo: **list-blockers** printed nothing after it.

## Batch parents

A batch is one parent with child tickets, worked in one branch and one pull request. On
GitHub the parent is an ordinary issue in the same repo and the children are its native
sub-issues. A batch parent's title starts with `Batch: ` (`references/batches.md`, "A batch
parent's title"); any other issue with sub-issues is not a batch parent. A parent is not a
ticket, so it is never on the board. Docs read 2026-11-13:
https://docs.github.com/en/rest/issues/sub-issues,
https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/adding-sub-issues,
and the GraphQL schema by introspection (`__type(name: "Issue")`).

Limits, from the docs: up to 100 sub-issues per parent, up to eight levels of nesting.
The REST page requires the sub-issue to belong to the same repository **owner** as the
parent, so a child may live in another repo of the same owner; it states no same-repo
rule. `parent_ref` is the parent's issue number (as a string). A parent's children
carry their own `repo`, which is the parent's repo for a same-repo batch.

## list-parents

Contract: every open issue in one repo that has sub-issues and a title starting with
`Batch: `, with its children, as
`{parent_ref, number, repo, title, url, labels, children: [{number, repo, state}]}`, at
most 100 parents. `parent_ref` is the parent's issue number; `labels` is a list of names;
`state` is `open` or `closed`.

```bash
gh api graphql --paginate -f query='query($endCursor:String){ repository(owner:"<owner>",name:"<repo>"){
  issues(states:OPEN,first:100,after:$endCursor){ pageInfo{hasNextPage endCursor}
    nodes{ number title url repository{nameWithOwner} labels(first:50){nodes{name}}
      subIssuesSummary{total} subIssues(first:100){nodes{number state repository{nameWithOwner}}} } } } }' \
  --jq '.data.repository.issues.nodes[] | select(.subIssuesSummary.total > 0) | select(.subIssues.nodes | length > 0) |
    select(.title | startswith("Batch: ")) | {
    parent_ref: (.number | tostring), number, repo: .repository.nameWithOwner, title, url,
    labels: [.labels.nodes[].name],
    children: [.subIssues.nodes[] | {number, repo: .repository.nameWithOwner, state: (.state | ascii_downcase)}]}'
```

`<owner>` and `<repo>` are the two halves of `<remote>`. GraphQL cannot filter issues by
"has sub-issues" (a `has:sub-issues` search qualifier is silently ignored and returns every
issue), so the query pages through every open issue, 100 per call, and keeps those whose
`subIssuesSummary.total` is above zero and whose title starts with `Batch: `; `--paginate`
follows the cursor. `subIssues(first:100)` covers the 100-per-parent limit in one page. Keep
the first 100 parents printed. Checked on a team repo with a few hundred open issues: every
parent titled `Batch: ` was printed with its labels and its children
(`{"number", "repo", "state"}` each), and parents with other titles were left out. The jq
output is one JSON object per parent, not an array. `subIssuesSummary.total` can lag a
change: right after a parent's only child moved to another parent, the old parent still
printed, with `children: []`, and read `total` 0 a moment later. The `length > 0` filter
leaves such a parent out.

## read-parent

Contract: a ticket's parent as `{parent_ref, number, repo, title, url, state, batch}`, or
null when it has none. `state` is `open` or `closed`. `batch` is true when the parent's title
starts with `Batch: `; a parent with `batch` false is not a batch, so the ticket is a single
for batching and is never attached to one (attaching would re-parent it).

```bash
gh api graphql -f query='{repository(owner:"<owner>",name:"<repo>"){issue(number:<n>){
  parent{number title url state repository{nameWithOwner}}}}}' \
  --jq '.data.repository.issue.parent | if . == null then null else {
    parent_ref: (.number | tostring), number, repo: .repository.nameWithOwner, title, url,
    state: (.state | ascii_downcase), batch: (.title | startswith("Batch: "))} end'
```

An issue with no parent prints `null`. REST has the same read,
`gh api repos/<owner>/<repo>/issues/<n>/parent`, but it answers HTTP 404 "No parent issue
found" (non-zero exit) when there is none, and returns the full REST issue object (`number`,
`title`, `html_url`, `state`, `id`), so use the GraphQL form. Checked both on a team repo: a
child of a parent with another title gives `batch` false, a child of a `Batch: ` parent gives
`batch` true, and an issue with no parent gives `null` (GraphQL, exit 0) and the 404 (REST).

## create-parent

Contract: creates the parent issue with a title, a body and labels (each label already
ensured). It is not added to the board. Returns `{parent_ref, number, url}`.

```bash
gh issue create --repo <remote> --title "<title>" --body-file <file> --label "<a>" --label "<b>"
```

This is **create-issue** without **add-to-board**. It prints the issue's URL; the number is
the last path segment, and `parent_ref` is that number. Checked 2026-11-24: it printed the
new issue's URL, and **list-parents** then printed the parent once it had a child.

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

Checked the id lookup on a team repo: it returns the numeric `id` and the node id (`I_...`).
The REST list of a parent's children (`gh api repos/<owner>/<repo>/issues/<parent>/sub_issues`,
`per_page` up to 100) matched the GraphQL list.

Checked the POST on 2026-11-24: it printed the parent, and **read-parent** on the child then
showed that parent with `batch` true. The same POST to a second parent moved the child there.
Two refusals, both HTTP 422 and exit 1: attaching a child to the parent it already has
(`Issue may not contain duplicate sub-issues`), and attaching a child that has another parent
without `replace_parent` (`Sub issue may only have one parent`). So treat the duplicate 422
as already attached, after **read-parent** confirms it. Verify every attach with
**read-parent** on the child.

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

Checked 2026-11-24 with **comment-parent** first: the parent read `closed` with both comments,
and its open sub-issue stayed `open`. Closing a parent leaves its children alone, so close
each child separately. UNVERIFIED: the `Closes #<parent>` keyword on a merged pull request
(no pull request was merged in the throwaway repo); it is the ordinary issue keyword.
