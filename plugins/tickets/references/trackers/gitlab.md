# Tracker adapter: GitLab

The exact commands for each tracker operation when the registry says
`tracker: gitlab`. Procedures name an operation (for example **set-lane**); this file
says how to run it. It uses the GitLab CLI (`glab`) and, where the CLI has no command,
`glab api` against the GitLab REST API v4, for gitlab.com or a self-managed host.

Every command below was run for real on 2026-10-08 with `glab` 1.121.0, signed in to
gitlab.com on the Free plan, against a private project in a personal namespace with a
project-scoped issue board. What that setup could not show is marked `UNVERIFIED:`
with the reason: group-scoped boards and labels, subgroups, a self-managed host, a
paid plan's scoped labels, a second assignee, and closing an issue in another project.
Run the first real queue against a group with `--dry-run`, then one ticket, before
trusting a wave.

The **status lane mode** (registry Board `Lanes: status`, see Terms) was checked on
2026-11-13 with `glab` 1.130.0 against a self-managed GitLab 19.5.4-ee (Premium) group
board whose lists are work item Statuses, spanning projects in subgroups. Its reads
(**capture-board**, **list-items**, the iid lookup in **set-lane**) ran for real. Its
write, the status mutation in **set-lane**, ran only against a work item id that does
not exist, which proves the input types and the error path and changes nothing; that a
real issue moves is UNVERIFIED until the first `--dry-run` queue's single ticket.

Read this file once, before the first tracker action of a run, and only when the
registry's tracker is `gitlab`. Run each operation as written below; never improvise a
command for one. `jq` must be installed. When the installed `glab` rejects a flag, run
`glab <command> --help`, tell the user which flag changed, and carry on with the equivalent.

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
- Batch parents
- list-parents
- read-parent
- create-parent
- attach-child
- comment-parent
- read-parent-item
- close-parent

## Terms used in the commands

- `<remote>` is the repo's registry Remote, the project path
  `group/subgroup/project` (or `username/project` in a personal namespace). `<n>` is
  the issue's project-level number (`iid`).
- `<enc>` is a path with each `/` written `%2F`, for example `my-group%2Fmy-app`.
  `<board path>` is the registry Board's group or project path, and `<scope>` is
  `groups` or `projects` as the registry's Board scope says (`group` becomes `groups`).
- `<host>` is the registry's Host. Every `glab api` call below carries
  `--hostname <host>`. For the other `glab` commands, export `GITLAB_HOST=<host>` for
  the whole run and pass `-R <remote>`. `-R` resolves on `GITLAB_HOST` (a lookup of an
  unknown host fails naming that host), works from any directory, and also accepts the
  full URL `-R https://<host>/<remote>`.
- **`glab api` quirks.** It has no `--jq` flag: pipe to `jq`. It sends a `POST` as soon
  as any `-f` or `-F` field is present, so a read that passes fields (a search, a
  filter) must say `-X GET`. It exits 1 on an HTTP error and prints the error body
  (`{"message":"404 Not found"}`); in a pipeline that `jq` then hides, so run the
  whole run's shell with `set -o pipefail` and treat a `null` where a value was
  expected as a failure. Quote every URL that contains `?`, or zsh refuses the line.
  `--paginate --output ndjson` works with a query string and prints one object per
  line, flattened across pages.
- **Lane mode.** The registry's Board `Lanes` value says which kind of board this is:
  `labels` (the default, also when the line is absent) or `status`. **Label mode** and
  **status mode** below each apply to one of them; everything not marked works in both.
  **capture-board** copies the mode into `tracker_ids.lane_mode`, which is how a worker
  (which gets `tracker_ids`, not the registry) knows it; a `tracker_ids` without the key
  is label mode.
- **Label mode.** The board is a set of label lists. **A lane is a label** and moving a card is
  swapping labels. The lane values in the registry are those labels (typically scoped,
  such as `status::ready`); priority values are labels too (`priority::1`). Scoped
  labels (`scope::value`) only replace one another on a paid plan. On the Free plan
  they are plain labels: adding `status::ready` to an issue that carries
  `status::in-review` leaves both on it. So **set-lane** and **set-priority** remove the
  other lane or priority labels explicitly, which works on every plan, and nothing
  else may add a lane or priority label: **add-label** with one leaves two lanes on the
  issue and **list-items** then reads its lane as null. A paid plan is the same
  commands with the removals as no-ops (UNVERIFIED: no paid account to run on).
- **Status mode.** The board's lists are the native work item Status (`listType: status`,
  `label` null; GitLab Premium or Ultimate). **A lane is a Status name** (`Ready`,
  `In progress`), every issue carries exactly one, and moving a card sets it. The REST API
  does not show Status: an issue object has no status field, and a status list reads
  `label: null, list_type: null` on the REST boards call. So **capture-board**, **list-items** and
  **set-lane** use GraphQL there. Lane labels play no part, nothing removes labels to move
  a card, and priority is still a label, set by **set-priority** as in label mode.
  Two Status facts change what a move means (GitLab docs, "Status", read 2026-11-13): a
  Status in the Done or Canceled category closes the issue, and closing an issue applies
  the issue type's default closed Status (Done on the checked board; all 100 most recently
  closed issues there read Done). A new or reopened issue gets the default open Status
  (Backlog there). UNVERIFIED: that closing through a merge request's closing keyword
  applies it too (no keyword-closed issue was found to read), and that setting an open
  Status on a closed issue reopens it.
- **GraphQL calls** go through `glab api --hostname <host> graphql -f query='<query>'`
  with each variable as another `-f name=value` (a missing variable is null; a null
  `$lane` in **list-items** filters nothing). `--paginate` follows
  `pageInfo { hasNextPage endCursor }` through a `$endCursor` variable and prints one JSON
  document per page, so read the pages with `jq -s` or a filter that runs per document. An
  error in the query or a refused mutation comes back as an `errors` list and `glab`
  exits 1 (checked for an unknown field and an unknown work item id); a mutation's own
  `errors` field in its payload must also be empty. Numbers (`iid`) come back as strings.
- **A label name that does not exist is created on the fly** by every command that adds
  labels (`labels=` on create, `add_labels` on edit, `--label` in `glab issue update`),
  with a default color (`#6699cc`) and no error. A typo therefore makes a new label.
  Names are case-sensitive and `Bug` and `bug` are two labels, so run **ensure-label**
  first and compare names exactly.
- **Quick actions run.** GitLab executes a line that starts with `/` in an issue
  description or a comment when it is a quick action (`/label ~bug`, `/close`,
  `/assign`), strips it from the saved text, and acts on it. Text that has a line
  starting with `/` (a path, a command) must sit inside a fenced code block or begin
  the line with a space; both are left alone.
- A GitLab color is written with a leading `#`. The registry writes colors without
  one, so add it when creating (`--color "#b60205"`; `b60205` is refused with
  `400 color must be a valid color code`) and strip it when reading.
- An issue's `web_url` may read `.../-/work_items/<n>` rather than `.../-/issues/<n>`.
  Both open the issue; the number is always the last path segment, and `iid` has it.
- `tracker_ids` is the object **capture-board** returns. It is stored in the state
  file's `project.tracker_ids` and read only by this file's commands.
- `item_ref` does not exist on GitLab; it is always null.
- A **review** is a merge request.
- Long text goes in a file; `-F description=@<file>`, `-F body=@<file>` and
  `--description-file` read it, so quoting never mangles it.
- Group-scoped boards list issues of every project in the group. A project-scoped
  board lists that project's issues only.

## auth-check

Contract: succeeds only when the CLI is signed in to the registry's host and can read
and write issues and the board; any failure or unparseable output is a failure.

```bash
glab auth status --hostname <host>
glab api --hostname <host> user | jq -r .username
```

`glab auth status` exits 0 when signed in. It exits 1 for a host the CLI has no login
for ("has not been authenticated") and for a token the host rejects (a 401 line in
its output). The second command reads the account and exits 1 on a missing or
rejected token; it needs `set -o pipefail` to be seen through the pipe. Neither
command shows the token's scopes (an OAuth sign-in prints none) and neither writes, so
a read-only token passes both and the first write fails with a 403: the token needs
the `api` scope. Not tested: the exit code after a real `glab auth logout`, because
that would sign the machine out; the two exit-1 cases above are the same "no usable
login" state.

## capture-board

Contract: resolves the board, lane and priority ids from the registry's Board, Lanes
and Priority values. Returns `tracker_ids`, `missing_lanes` (lane roles whose value is
not on the board), `missing_priorities` (priority roles whose value is not on the
board) and `has_priority` (the board has a Priority field). The caller decides which
missing value halts a run.

```bash
glab api --hostname <host> "<scope>/<enc board path>/boards"
glab api --hostname <host> --paginate --output ndjson "<scope>/<enc board path>/labels?per_page=100"
```

Pick the board whose `name` equals the registry's Board (or whose `id` equals it, when
the registry gives a number). The boards call already carries each board's `lists`;
take each list's `label.name` in `position` order (a separate `.../boards/<id>/lists`
call returns the same). The board object also has `hide_backlog_list` and
`hide_closed_list`. In label mode `tracker_ids` is:

```json
{
  "scope": "groups", "board_path": "<board path>", "board_id": 12, "lane_mode": "labels",
  "list_labels": ["status::ready", "status::in-progress"],
  "priority_labels": ["priority::1", "priority::2"]
}
```

In label mode, a registry lane value that is not in `list_labels` goes in `missing_lanes`:
the board has no column for it, so **set-lane** would move the issue off the board. Two roles
have a column without a list. Every board has an **Open** list, which shows each open
issue that carries none of the other lists' labels, and a **Closed** list, which shows
every closed issue. The `backlog` role counts as on the board while `hide_backlog_list`
is false, and the `done` role while `hide_closed_list` is false (both were false on the
test board; hiding a list is a setting that was not toggled to see what changes): a ticket labelled
`status::backlog` shows in Open (checked against the board's own issue counts), and a
closed ticket shows in Closed whatever lane label it still carries. Leave those two
roles out of `missing_lanes` when their built-in list is shown, and list them when it
is hidden. Any other value without a list is missing.

**Status mode.** Resolve the board id from the boards call above (the REST lists carry no
status, so ignore them), then read the lists and the issue type's Statuses in one call;
`<field>` is `group` or `project` as the Board scope says:

```bash
glab api --hostname <host> graphql -f path="<board path>" -f board="gid://gitlab/Board/<board id>" \
  -f query='query($path: ID!, $board: BoardID!) {
  <field>(fullPath: $path) { board(id: $board) { name lists { nodes { listType status { id name } } } } }
  namespace(fullPath: $path) { workItemTypes(name: ISSUE) { nodes { widgetDefinitions {
    ... on WorkItemWidgetDefinitionStatus { allowedStatuses { id name } defaultClosedStatus { name } } } } } }
}' | jq -c '{
  status_ids: ([.data.<field>.board.lists.nodes[] | select(.listType == "status") | {(.status.name): .status.id}] | add),
  allowed: [.data.namespace.workItemTypes.nodes[0].widgetDefinitions[] | select(.allowedStatuses) | .allowedStatuses[].name],
  closed_default: ([.data.namespace.workItemTypes.nodes[0].widgetDefinitions[] | select(.allowedStatuses) | .defaultClosedStatus.name] | .[0])}'
```

`tracker_ids` is then
`{"scope", "board_path", "board_id", "lane_mode": "status", "status_ids": {"Ready": "gid://gitlab/WorkItems::Statuses::Custom::Status/9", ...}, "priority_labels"}`.
A registry lane value that is not a key of `status_ids` (compare names exactly) goes in
`missing_lanes`; there is no exception for backlog or done, because every Status the
board shows is a list of its own. A list Status the issue type does not allow (absent
from `allowed`) counts as missing too, since the mutation would refuse it. When the done
lane is not `closed_default`, print one warning for the run that names both: closing an
issue sets the closed default, so closed tickets will not read as done.

The board must match the mode. A board with no `listType == "status"` list (so
`status_ids` is null) is a label board, and in label mode a list whose `label` is null
is a Status list. Either mismatch halts the run with a message that names the registry's
`Lanes` mode and the board's real kind, never a list of missing lanes. This matters when
`--project`, `--owner` or a pasted URL points the run at another board than the
registry's: the mode and the lane values still come from the registry. Priority labels come from the labels
call as in label mode. On the checked board the call returned eight statuses (Backlog,
Ready, In progress, Blocked, In review, Done, Skip, Duplicate) with `closed_default` Done;
the board's `hideBacklogList` and `hideClosedList` were both true, and neither matters
in status mode.

From the labels call, `priority_labels` holds the registry's priority values that exist as a
label (compare names exactly); the others go in `missing_priorities`, and
`has_priority` is true when `priority_labels` is not empty. GitLab has no Priority
field; labels stand in for it. The project labels call lists the project's own labels.
The group labels call does **not** list labels defined inside the group's projects
(checked 2026-11-13: `P0` to `P3` existed only as project labels of one project, and the
group call, also with `only_group_labels=false`, returned none of them). So on a group
board also run **list-labels** for each registry repo on the board, and count a priority
value as present when it is a group label or a label of any of those repos. Defining
priority labels at the group avoids the extra calls. The group boards call
(`groups/<enc>/boards`) answered 200 with an empty list on the first test account; the
group board on the self-managed host was read (see the status mode note at the top).

## list-items

Contract: every board item, optionally only those in one lane, as
`{item_ref, number, repo, type, title, lane, priority, labels, assignees}`. `repo` is the
Remote form (`owner/repo`). `type` is `issue`, `review` or `other` (a draft item).
`lane` and `priority` are registry values, or null when unset. `assignees` is a list of logins, empty when unassigned. `number` is null for a
draft item.

Label mode:

```bash
glab api --hostname <host> --paginate --output ndjson \
  "<scope>/<enc board path>/issues?state=opened&per_page=100[&labels=<lane value>]" |
jq -c --argjson lanes '["<every lane value>"]' --argjson prios '["<every priority value>"]' '{
  item_ref: null, number: .iid, repo: (.references.full | sub("#[0-9]+$"; "")),
  type: "issue", title: .title,
  lane: ([.labels[] | select(. as $l | $lanes | index($l))] | if length == 1 then .[0] else null end),
  priority: ([.labels[] | select(. as $l | $prios | index($l))] | .[0]),
  labels: .labels, assignees: [.assignees[].username]}'
```

Percent-encode any space in a label inside the query; a `::` in a lane value needs no
encoding. Issues come back newest first. The issues endpoints return issues only, so
`type` is always `issue`; merge requests never appear. An issue with no lane label is
listed with `lane` null (it sits in the board's Open list). `lane` is also null for an
issue with several lane labels; **set-lane** never leaves several, and running it
once repairs one. A closed issue is not listed (`state=opened`), which differs from
GitHub, where a closed issue stays on the board as an item. A caller that must find
closed issues still sitting in a lane (`daily-grooming`'s settle step) runs the same
call with `state=closed` in place of `state=opened`, keeps the items whose `lane` is
set and is not the done lane, and moves each with **set-lane**. Verified 2026-10-08:
a merge that closes an issue leaves its lane label on, so this is how a closed ticket
reaches done.
UNVERIFIED: that a group-scoped call includes issues of projects in subgroups; the
test account's group has no subgroup. If it does not, run the call once per subgroup
in the registry's repo table.

Status mode, one call for a group or a project board (`namespace` takes either path):

```bash
glab api --hostname <host> graphql --paginate -f path="<board path>" -f state=opened \
  [-f lane="<lane value>"] -f query='query($path: ID!, $state: IssuableState, $lane: String, $endCursor: String) {
  namespace(fullPath: $path) {
    workItems(state: $state, types: [ISSUE], includeDescendants: true,
              status: {name: $lane}, first: 100, after: $endCursor) {
      pageInfo { hasNextPage endCursor }
      nodes { iid title namespace { fullPath } widgets {
        ... on WorkItemWidgetStatus { status { name } }
        ... on WorkItemWidgetLabels { labels { nodes { title } } }
        ... on WorkItemWidgetAssignees { assignees { nodes { username } } } } }
    }
  }
}' |
jq -c --argjson lanes '["<every lane value>"]' --argjson prios '["<every priority value>"]' '
  .data.namespace.workItems.nodes[] |
  ([.widgets[] | select(has("labels")) | .labels.nodes[].title]) as $labels | {
  item_ref: null, number: (.iid | tonumber), repo: .namespace.fullPath, type: "issue", title,
  lane: ([.widgets[] | select(has("status")) | .status.name // empty | select(. as $s | $lanes | index($s))] | .[0]),
  priority: ([$labels[] | select(. as $l | $prios | index($l))] | .[0]),
  labels: $labels, assignees: [.widgets[] | select(has("assignees")) | .assignees.nodes[].username]}'
```

Leave out `-f lane=` to list every lane. Issues come back newest first. A Status that is
not a registry lane (Skip and Duplicate on the checked board) reads as `lane` null. The
group form includes projects in subgroups (`includeDescendants`, ignored for a project
path; checked: the group call returned issues of `rcf/dev-tools/*` projects). Checked on
the group board: 459 open issues across 12 projects, every one with a Status, in about
25 seconds; the `Ready` filter returned 25 in 3 seconds, the same 25 the unfiltered call
put in Ready. The settle step's closed call is the same command with `-f state=closed`,
run once for each lane other than done with that lane as `-f lane=` (the variable takes
one value), which keeps it to the few tickets it can act on instead of every closed issue; it found none on the checked board, since closing
applies Done (see Terms).

## read-issue

Contract: `{title, body, labels, assignees, state, comments[{created, body}], created, updated}`
for one issue; `assignees` is a list of logins, empty when unassigned; `state` is `open` or `closed`.

```bash
glab api --hostname <host> "projects/<enc>/issues/<n>" | jq '{
  title, body: .description, labels, assignees: [.assignees[].username], state: (if .state == "opened" then "open" else .state end),
  created: .created_at, updated: .updated_at}'
glab api --hostname <host> --paginate --output ndjson "projects/<enc>/issues/<n>/notes?sort=asc&per_page=100" |
  jq -c 'select(.system | not) | {created: .created_at, body}'
```

Combine the two into the contract's object, with the second command's lines as
`comments`. The notes call also returns system notes ("assigned to @x", "mentioned in
merge request !1", "mentioned in commit ..."); the `select` drops them. Label changes
leave no note. An issue with no comments prints nothing from the second command. A
number that is not an issue prints `{"message":"404 Not found"}` and exits 1.

## issue-state

Contract: `open` or `closed` for each issue in a list of numbers in one repo, with
the close time when closed.

```bash
glab api --hostname <host> "projects/<enc>/issues/<n>" |
  jq '{state: (if .state == "opened" then "open" else .state end), closed_at}'
```

Run it once per number. `closed_at` is null while open. A missing issue exits 1 with
the 404 body, and `jq` then prints `state: null`: that is a failure, and an unknown state never counts as open.

## search-issues

Contract: issues of any state in one repo matching keywords, as
`{number, title, state, url}`, newest first, at most 20.

```bash
glab api --hostname <host> -X GET "projects/<enc>/issues" -f state=all -f search="<keywords>" -f per_page=20 |
  jq -c '.[] | {number: .iid, title, state: (if .state == "opened" then "open" else .state end), url: .web_url}'
```

The search covers titles and descriptions, and every keyword must appear (in any
order, in either field). It does not look inside comments, and a word that sat inside
backticks in the text was not matched.

To find the model-fit notes workers leave, which are comments, search the project's
comments instead:

```bash
glab api --hostname <host> -X GET "projects/<enc>/search" -f scope=notes -f search="Model-fit note" |
  jq -c '.[] | select(.noteable_type == "Issue") | {number: .noteable_iid, body}'
```

It returns one object per matching comment (so an issue can appear twice), newest
first; read the issue with **read-issue** for its state and the rest of its comments.
A merge request's comments come back too, with `noteable_type` `MergeRequest`, which
the `select` drops.

## current-user

Contract: the login of the account the CLI is signed in as, on the registry's host.
Fails when it cannot be read; an empty or unparseable answer is a failure.

```bash
glab api --hostname <host> user | jq -r .username
```

## assign

Contract: adds one login to an issue's assignees, leaving the other assignees alone.

```bash
glab issue update <n> -R <remote> --assignee "+<login>"
```

The `+` is what adds; the same flag without it replaces every assignee. Assigning a
login already on the issue changes nothing and exits 0. An unknown login prints
`Failed to find user by name`, exits 1 and leaves the issue as it was. UNVERIFIED: that
a second login added with `+` keeps the first (the `glab issue update --help` text says
it does; the test account is the only user, so no second assignee was tried).

## comment

Contract: posts text as a new comment on one issue.

```bash
glab issue note <n> -R <remote> -m "<text>"
```

It prints the comment's URL. For a long or multi-line body, set it in a shell variable
first (`-m "$BODY"`), or post it through the API:
`glab api --hostname <host> -X POST "projects/<enc>/issues/<n>/notes" -F body=@<file>`.
Both keep quotes, `$` and backticks as written. A line that starts with `/` runs as a
quick action (see Terms); fence it.

## set-lane

Contract: moves one issue's board item to the lane named by a lane role. The lane
value comes from the registry's Lanes table for the role. When the value is in
`missing_lanes`, skip the move, log a warning and carry on; never block on it.

Label mode:

```bash
glab api --hostname <host> -X PUT "projects/<enc>/issues/<n>" \
  -f add_labels="<lane value>" -f remove_labels="<every other lane value, comma separated>"
```

It prints the updated issue; `.labels` has the lane value and none of the others. The
issue joins the board's column for that label (checked against the board's issue
counts). The fields reach GitLab as a `PUT` body and work as written. Moving an issue
twice (ready, then in-progress, then in-review) left only the last lane each time.
Listing a lane the issue does not carry in `remove_labels` is not an error, repeating
the same move changes nothing, and an empty `remove_labels` is accepted. It works on
a closed issue too, which is how the done lane is set. The lane label is not removed
when a merge closes the issue, so a closed ticket keeps `status::ready` until
**set-lane** is run for done.

A value is also missing when it is not in `list_labels` (apart from the backlog and
done roles, see **capture-board**).

Status mode: look up the issue's work item id, then set its Status to the lane's id from
`tracker_ids.status_ids`:

```bash
glab api --hostname <host> graphql -f path="<remote>" -f iid="<n>" \
  -f query='query($path: ID!, $iid: String!) { project(fullPath: $path) { workItems(iids: [$iid], first: 1) { nodes { id } } } }' |
  jq -e -r '.data.project.workItems.nodes[0].id // error("no such issue")'
glab api --hostname <host> graphql -f id="<work item id>" -f status="<status id>" \
  -f query='mutation($id: WorkItemID!, $status: WorkItemsStatusesStatusID!) {
  workItemUpdate(input: {id: $id, statusWidget: {status: $status}}) {
    workItem { widgets { ... on WorkItemWidgetStatus { status { name } } } } errors } }' |
  jq -e '.data.workItemUpdate.errors == [] and
    ([.data.workItemUpdate.workItem.widgets[] | select(has("status")) | .status.name] == ["<lane value>"])'
```

The first call prints `gid://gitlab/WorkItem/<id>`; a number that is not an issue in that
project makes `jq` exit 5, and empty output (a failed `glab`) makes `jq -e` exit 4. Any
non-zero exit or empty id is a failure; never run the mutation without an id. The second succeeds only when the payload's `errors` is empty
and the Status read back is the lane value (`jq -e` exits 1 otherwise). The status id
comes from **capture-board**, not from a name, so a Status renamed since capture fails
loudly rather than landing elsewhere (the input also takes `name:` in place of `status:`,
matched case-insensitively; it is not used here for that reason). Setting a Done or
Canceled category Status closes the issue (see Terms), which is why only
`daily-grooming` ever sets the done lane. UNVERIFIED: that the mutation moves a real issue;
it was run only against a nonexistent work item id, where `glab` exited 1 with "The
resource that you are attempting to access does not exist" and the input types were
accepted.

## set-priority

Contract: sets one issue's board item to the priority named by a priority role. Same
skip rule as **set-lane** for a value in `missing_priorities`.

```bash
glab api --hostname <host> -X PUT "projects/<enc>/issues/<n>" \
  -f add_labels="<priority value>" -f remove_labels="<every other priority value, comma separated>"
```

Checked the same way: the old priority label is gone, the new one is on, other labels
are untouched, and an issue with no priority label gets just the new one. `add_labels`
creates a missing label on the fly (see Terms), so when the priority value is a project
label of other repos only (see **capture-board**), run **ensure-label** in this issue's
repo first, with color `ededed` and description `Priority: <name>`.

## add-label

Contract: adds one label that already exists in the repo to one issue.

```bash
glab issue update <n> -R <remote> --label "<name>"
```

It prints the issue's URL last. A name that does not exist is created (see Terms), so
only pass a name **ensure-label** has confirmed. Never use it for a priority label or a
lane value: use **set-priority** or **set-lane**. In status mode a lane value is a Status
name, never a label, and adding it as one only creates a stray label.

## remove-label

Contract: removes one label from one issue; a label the issue does not carry is not
an error worth stopping for.

```bash
glab issue update <n> -R <remote> --unlabel "<name>"
```

It exits 0 and says `removed labels <name>` whether the issue carried the label or not,
and even when no such label exists in the project. There is no failure to handle.

## ensure-label

Contract: makes sure a label exists in the repo, creating it with the registry's
color and description when missing. Never changes an existing label.

```bash
glab api --hostname <host> -X GET "projects/<enc>/labels" -f search="<name>" |
  jq -r '.[].name'
```

The search is a case-insensitive substring match (`blocked` also returns
`status::blocked`; `BUG` returned both `Bug` and `bug`), so compare each returned name
to `<name>` exactly. When none matches:

```bash
glab label create -R <remote> --name "<name>" --color "#<color>" --description "<description>"
```

The registry's colors are written without a leading `#`; GitLab refuses a color
without one. Creating a name that already exists exits 1 with `409 Label already
exists`. The labels call also returns labels inherited from ancestor groups (its
`include_ancestor_groups` parameter defaults to true, per the documentation), so a
group label counts as existing. UNVERIFIED: the inheritance, because a personal
namespace has no ancestor group.

## list-labels

Contract: every label in the repo as `{name, color, description}`.

```bash
glab api --hostname <host> --paginate --output ndjson "projects/<enc>/labels?per_page=100" |
  jq -c '{name, color: (.color | ltrimstr("#")), description}'
```

GitLab returns the color with a leading `#`; the `ltrimstr` makes it match the
registry's form. UNVERIFIED: that group labels appear in this list (no group labels
existed to look for).

## create-issue

Contract: creates an issue with a title, a body and labels (each label already
ensured), then runs **add-to-board**. Returns `{number, url, item_ref}`.

```bash
glab api --hostname <host> -X POST "projects/<enc>/issues" \
  -f title="<title>" -F description=@<file> -f labels="<a>,<b>" |
  jq '{number: .iid, url: .web_url, item_ref: null}'
```

The title goes in with `-f` so a title such as `2024` stays a string (it did). In label
mode the lane label may be in the label list or set afterwards with **set-lane**; either
way it is what puts the issue on the board. In status mode the new issue starts in the
default open Status (Backlog on the checked board); run **set-lane** for any other lane. A body line starting with `/` runs as a quick
action (see Terms). The `url` ends in `/-/work_items/<n>`.

## add-to-board

Contract: puts an existing issue on the board and returns its `item_ref`.

On GitLab there is nothing to run, and `item_ref` is null. In label mode an issue is on
the board when it carries a lane label: **set-lane** (or the lane label in
**create-issue**'s label list) is the add. An issue with a list's label shows in that
list; one with no list label shows in Open. In status mode every open issue of the
board's group or project already has a Status, so it shows in that Status's list.

## edit-issue

Contract: replaces an issue's body, and its title when one is given.

```bash
glab issue update <n> -R <remote> --description-file <file> [--title "<title>"]
```

Both the body and a numeric title such as `2025` come through as written. A body line
starting with `/` runs as a quick action (see Terms).

## close-issue

Contract: closes one issue with a closing comment.

```bash
glab issue note <n> -R <remote> -m "<comment>"
glab issue close <n> -R <remote>
```

`glab issue close` has no comment flag, so the comment goes first. Closing an issue
that is already closed exits 0 with the same message; a number that does not exist
exits 1. In status mode closing also applies the default closed Status (see Terms).

**Closing keywords for a commit message.** The keyword closes the issue when the
commit is merged into, or pushed to, the project's default branch. Run against a
merge request merged into `main`:

- Same project: `Closes #<n>` closed the issue, and so did `Fixes #<n>`, `Resolves #<n>`
  and `Implements #<n>`.
- The keyword closes the issue from the merge request's description, and equally from
  a commit message on the merge request's branch with nothing in the description.
- `Refs #<n>` and a bare `#<n>` in a commit message or description only link the
  issue ("mentioned in merge request"); it stayed open.
- Another project, closing: `Closes <group>/<project>#<n>`. UNVERIFIED: only one test
  project existed, so closing across projects was not tried (the documented form).
- Another project, not closing: `Refs <group>/<project>#<n>`. UNVERIFIED for the same
  reason.
- A project can turn automatic closing off (the project setting "Auto-close referenced
  issues on default branch"; the API field is `autoclose_referenced_issues`). With it
  off, a merged merge request carrying `Closes #<n>` left the issue open, and
  **verify-closed** reported `opened` on all five tries.
- A merge right after another merge can fail with `405 Method Not Allowed` for a few
  seconds while GitLab recomputes the second request's status; running
  `glab mr merge` again succeeded.

## verify-closed

Contract: confirms an issue is closed, polling up to 5 times, 2 seconds apart. Returns
true on the first `closed`.

```bash
glab api --hostname <host> "projects/<enc>/issues/<n>" | jq -r '.state'
```

Repeat until it prints `closed` or the fifth try has failed (`opened` means still open).
A merge that carries a closing keyword closed the issue before the first poll in every
run, so the loop normally ends on try 1.

## open-review

Contract: opens a review from a pushed branch into `<base>`, the repo's default branch
as the caller resolved it (never assumed to be `main`), with a title, a body and, when
the caller asks for one, one label (already ensured); leave the label argument out
otherwise. Returns the review URL.

```bash
glab mr create -R <remote> --source-branch <branch> --target-branch <base> --title "<title>" \
  --description-file <file> [--label "<label>"] --yes
glab mr list -R <remote> --source-branch <branch> --output json --jq '.[0].web_url'
```

The first command opens a merge request into `<base>` and prints the URL as its last
line; the second reads it back. `glab mr create` works with `-R` alone from a
directory outside the project's clone, and from inside it, with or without `--label`.
The branch is already pushed, so no `--push`. The `mr list` form lists open merge
requests only (its help text gives `--all` for every state) and `--jq` is accepted
there, unlike on `glab api`. A line starting with `/` in the description runs as a quick
action (see Terms).

## list-blocked

Contract: open issues in one repo carrying the blocked label, as `{number, body}`, at
most 100.

```bash
glab api --hostname <host> -X GET "projects/<enc>/issues" -f state=opened -f labels="<blocked label>" -f per_page=100 |
  jq -c '.[] | {number: .iid, body: .description}'
```

The label filter is an exact name: `blocked` did not return an issue labelled only
`status::blocked`.

## list-open-issues

Contract: every open issue in one repo as `{number, title, body, labels, assignees}`, newest first, at most 1000. `labels` is a list of names and `assignees` a list of logins. An issue missing from this list is closed or beyond the cap, so a caller that means to act on its absence confirms it with **issue-state** first.

```bash
glab api --hostname <host> --paginate --output ndjson "projects/<enc>/issues?state=opened&order_by=created_at&sort=desc&per_page=100" |
  jq -c '{number: .iid, title, body: .description, labels, assignees: [.assignees[].username]}' | head -n 1000
```

`--paginate` and the query string combine as written (a `per_page=2` run returned all
five issues across three pages, newest first).

## list-open-reviews

Contract: every open review in one repo as `{number, url, closes}`, newest first, at most 1000. `closes` lists the numbers of the issues in the same repo that the review closes when it merges (a closing keyword in its description); it is empty for a review that only mentions an issue.

```bash
glab api --hostname <host> "projects/<enc>" | jq .id
glab api --hostname <host> --paginate --output ndjson "projects/<enc>/merge_requests?state=opened&order_by=created_at&sort=desc&per_page=100" |
  jq -c '{number: .iid, url: .web_url}' | head -n 1000
glab api --hostname <host> "projects/<enc>/merge_requests/<number>/closes_issues" |
  jq -c --argjson pid <project id> '[.[] | select(.project_id == $pid) | .iid]'
```

The first command gives the project's numeric id, once. Run the third once per merge
request from the second and join its list on as `closes`. The `closes_issues` objects
carry `project_id` and `iid` but a null `references`, so the same-repo test compares
`project_id`, since `references` is null. It also lists issues closed by a keyword
in a commit message on the branch, as well as those named in the description. GitLab fills the list
in about a second after a merge request opens: asked at once it returns `[]`, so a
caller that opened the review itself waits a few seconds before reading it.
UNVERIFIED: that an issue in another project is left out by the `project_id` test;
only one test project existed, so every listed issue was in the same project.

## review-state

Contract: `open`, `merged` or `closed` for one review (a closed review that was not merged reads `closed`). Fails when the number is not a review in that repo.

```bash
glab api --hostname <host> "projects/<enc>/merge_requests/<n>" |
  jq -r 'if .state == "opened" or .state == "locked" then "open" else .state end'
```

GitLab's states are `opened`, `closed`, `locked` and `merged`; `locked` is the short moment while a merge completes and reads as `open`. A merge request left open printed `open`, one closed unmerged printed `closed`, and one merged printed `merged`. A number that is not a merge request exits 1 with a 404 body. UNVERIFIED: the `locked` state, which is too brief to catch.

## Batch parents

Used only when the registry's Batches `mode` is `epics` (`references/batches.md`). A parent
is a **group epic** in the board's group, and its children are issues attached to it
through the epic's hierarchy. On the checked self-managed host an issue cannot be the
parent of another issue, so an epic is the only native parent. Epics are not issues: the
REST issues calls and the issue board never show them, they carry no Status (the epic
type has no status widget), and a merge request's closing keyword does not close one
(GitLab docs, "Epics" and "Closing issues automatically": keywords close issues only;
UNVERIFIED by a merge). Every call below is GraphQL (see Terms). `<group>` is the
registry's Board path (on a project board, its parent group).

Checked 2026-11-13 on the self-managed host: **list-parents**, **read-parent** and
**read-parent-item** ran for real against the group's one open epic and its six children.
Each write (**create-parent**, **attach-child**, **comment-parent**, **close-parent**) ran
only against a namespace or work item that does not exist: GitLab accepted the input
types and refused the target, so nothing changed. That a write changes a real epic is
UNVERIFIED until the first batch.

## list-parents

Contract: every open parent with its children, as `{parent_ref, number, repo, title, url,
labels, children: [{number, repo, state}]}`. `parent_ref` is the epic's work item id,
`number` its iid, `repo` the group path; a child's `state` is `open` or `closed`.

```bash
glab api --hostname <host> graphql --paginate -f path="<group>" \
  -f query='query($path: ID!, $endCursor: String) { group(fullPath: $path) {
  workItems(types: [EPIC], state: opened, first: 50, after: $endCursor) {
    pageInfo { hasNextPage endCursor }
    nodes { id iid title webUrl widgets {
      ... on WorkItemWidgetLabels { labels { nodes { title } } }
      ... on WorkItemWidgetHierarchy { children(first: 100) { nodes {
        iid state namespace { fullPath } workItemType { name } } } } } } } } }' |
jq -c '.data.group.workItems.nodes[] | {
  parent_ref: .id, number: (.iid | tonumber), repo: "<group>", title, url: .webUrl,
  labels: [.widgets[] | select(has("labels")) | .labels.nodes[].title],
  children: [.widgets[] | select(has("children")) | .children.nodes[] | select(.workItemType.name == "Issue") |
    {number: (.iid | tonumber), repo: .namespace.fullPath, state: (.state | ascii_downcase)}]}'
```

Children of any project in the group come back, each with its own `repo`; a child epic
(sub-epic) is dropped by the `Issue` filter. The checked epic printed six children, five
`open` and one `closed`. A batch never nears 100 children, so the first page of children
is all of them.

## read-parent

Contract: a ticket's parent as `{parent_ref, number, repo, title, url, state}`, or null.

```bash
glab api --hostname <host> graphql -f path="<remote>" -f iid="<n>" \
  -f query='query($path: ID!, $iid: String!) { project(fullPath: $path) { workItems(iids: [$iid], first: 1) {
  nodes { id widgets { ... on WorkItemWidgetHierarchy { parent {
    id iid title webUrl state namespace { fullPath } } } } } } } }' |
jq -e -c '.data.project.workItems.nodes[0] // error("no such issue") |
  [.widgets[] | select(has("parent")) | .parent][0] |
  if . == null then null else {parent_ref: .id, number: (.iid | tonumber),
    repo: .namespace.fullPath, title, url: .webUrl, state: (.state | ascii_downcase)} end'
```

`jq -e` exits 1 on the `null` of a ticket with no parent, which is an answer, not a
failure: read the output, and treat only a missing issue (exit 5) or empty output as a
failure. Checked: a child of the epic printed it; an issue with no parent printed `null`.

## create-parent

Contract: creates a parent with a title and a body file, and returns `{parent_ref, number,
url}`. Labels are not set on an epic; the area lives in its title.

```bash
glab api --hostname <host> graphql -f path="<group>" \
  -f query='query($path: ID!) { namespace(fullPath: $path) { workItemTypes(name: EPIC) { nodes { id } } } }' |
  jq -e -r '.data.namespace.workItemTypes.nodes[0].id'
glab api --hostname <host> graphql -f ns="<group>" -f type="<epic type id>" -f title="<title>" \
  -f body="$(cat <file>)" -f query='mutation($ns: ID!, $type: WorkItemsTypeID!, $title: String!, $body: String) {
  workItemCreate(input: {namespacePath: $ns, workItemTypeId: $type, title: $title,
    descriptionWidget: {description: $body}}) { workItem { id iid webUrl } errors } }' |
jq -e -c '.data.workItemCreate | select(.errors == []) | .workItem |
  {parent_ref: .id, number: (.iid | tonumber), url: .webUrl}'
```

The first call gives the epic type's id once per run (`gid://gitlab/WorkItems::Type/8` on
the checked host). A body line starting with `/` runs as a quick action (see Terms).
UNVERIFIED: the create itself (run only against a group that does not exist).

## attach-child

Contract: makes one issue a child of a parent, replacing any parent it had.

```bash
glab api --hostname <host> graphql -f id="<child work item id>" -f parent="<parent_ref>" \
  -f query='mutation($id: WorkItemID!, $parent: WorkItemID!) {
  workItemUpdate(input: {id: $id, hierarchyWidget: {parentId: $parent}}) {
    workItem { widgets { ... on WorkItemWidgetHierarchy { parent { id } } } } errors } }' |
jq -e '.data.workItemUpdate.errors == [] and
  ([.data.workItemUpdate.workItem.widgets[] | select(has("parent")) | .parent.id] == ["<parent_ref>"])'
```

The child's work item id comes from the iid lookup in **set-lane**. It succeeds only when
the parent read back is the one asked for. UNVERIFIED: that a child with a parent is moved
rather than refused, and the attach itself (run only against a work item that does not
exist).

## comment-parent

Contract: posts text as a new comment on a parent.

```bash
glab api --hostname <host> graphql -f id="<parent_ref>" -f body="$(cat <file>)" \
  -f query='mutation($id: NoteableID!, $body: String!) { createNote(input: {noteableId: $id, body: $body}) { note { url } errors } }' |
jq -e -r '.data.createNote | select(.errors == []) | .note.url'
```

UNVERIFIED: run only against a work item that does not exist.

## read-parent-item

Contract: `{title, body, state, comments[{created, body}]}` for one parent.

```bash
glab api --hostname <host> graphql -f path="<group>" -f iid="<number>" \
  -f query='query($path: ID!, $iid: String!) { namespace(fullPath: $path) { workItem(iid: $iid) {
  title description state widgets { ... on WorkItemWidgetNotes { discussions(first: 100) { nodes {
    notes { nodes { system body createdAt } } } } } } } } }' |
jq -e -c '.data.namespace.workItem // error("no such parent") | {title, body: .description,
  state: (.state | ascii_downcase),
  comments: [.widgets[] | select(has("discussions")) | .discussions.nodes[].notes.nodes[] |
    select(.system | not) | {created: .createdAt, body}]}'
```

Checked on the group's epic: its title and body came back, with no comments yet.

## close-parent

Contract: closes one parent with a closing comment.

```bash
# comment first with comment-parent, then:
glab api --hostname <host> graphql -f id="<parent_ref>" \
  -f query='mutation($id: WorkItemID!) { workItemUpdate(input: {id: $id, stateEvent: CLOSE}) { workItem { state } errors } }' |
jq -e '.data.workItemUpdate.errors == [] and .data.workItemUpdate.workItem.state == "CLOSED"'
```

UNVERIFIED: run only against a work item that does not exist.
