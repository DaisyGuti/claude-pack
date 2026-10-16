# Execute mode: drafted commands, one step at a time

Execute mode runs only after the user asks for it. Every step below is a DRAFT until the user says
go for that step. Reads can run freely. Writes never run without the go.

Sources: `glab` and `gh` help output (versions installed on the machine; run `glab --help` and
`gh --help` for flags if a command is refused), and the API pages named in the other references.

## Contents

- [Step protocol](#step-protocol)
- [Secrets protocol](#secrets-protocol)
- [Step catalogue](#step-catalogue)
- [Steps that need a second confirmation](#steps-that-need-a-second-confirmation)

## Step protocol

For each step, show this block, then stop and wait:

```
STEP n of m: <what it does in one sentence>
Where it writes: <GitLab project / GitHub repository / Google Cloud project / local clone>
Undo: <how to reverse it, or "cannot be undone">
Command:
  <the exact command, with placeholders filled from the plan>
Reply "go" to run this step, or tell me what to change.
```

Rules:

1. A go applies to the step just shown. A reply such as "do all of it" covers the steps displayed
   in that message and no step Claude has not yet shown.
2. After a step runs, show the result (status, IDs and URLs only) and run the matching read
   check before offering the next step.
3. If a command fails, stop. Show the error, say what it likely means, and propose a corrected
   draft. Do not retry a write on your own.
4. Never run a command that contains a secret value. Never ask for one. See the secrets protocol.
5. Steps that delete or archive on GitHub, or remove Google Cloud trust, need the second
   confirmation described at the end.
6. If the user changes a step, redraft it from the top and ask again.

## Secrets protocol

- List secret NAMES only. The inventory prints names and never values.
- The user enters each value at a silent prompt in their own terminal, or pipes it from their
  password manager's command line. A value never appears in chat, in a file in the repository, in
  shell history or on a command line.
- Do not run commands that print variable values (`glab variable get`, `env`, `printenv`) in the
  session. `glab variable list` shows names and settings and is allowed. `glab variable get` and
  `glab variable export` print values; do not run them in the session.
- If the user pastes a secret into chat anyway: do not repeat it, tell them to revoke and replace
  it, and continue with the plan.

## Step catalogue

Replace the capitalised placeholders. `-R GROUP/PROJECT` selects the GitLab project. For a
self-managed host add `--hostname GITLAB_HOST` to `glab api`, or export `GITLAB_HOST`.

### 0. Preflight reads (no go needed)

```sh
glab auth status
gh auth status
glab api version                                     # instance version (self-managed: compare with the docs)
gh api repos/OWNER/NAME --jq '{id, default_branch, private, archived}'
glab api "groups?search=GROUP" --jq '.[].full_path'
```

### 1. Create the target group (only if it does not exist)

`glab` has no group-create command in the version checked; use the API. Private visibility for a
government product unless the plan says otherwise.

```sh
glab api --method POST groups -f name="GROUP NAME" -f path=GROUP -f visibility=private
```

Do NOT create the project first when importing: the import creates the project. For a project with
no import, use `glab repo create GROUP/NAME --private`.

### 2. Run the import

See references/importer.md ("Drafted API command"). The user runs it in their own terminal. Then
poll the read-only status:

```sh
glab api projects/PROJECT_ID/import --jq '{import_status, import_error}'
```

### 3. Create variables (names only; values by the user)

Non-secret values (the plan's `vars.*` names) can be set directly:

```sh
glab variable set GCP_PROJECT_NUMBER -v 123456789012 -R GROUP/PROJECT
```

Secrets, one at a time, typed or piped by the user:

```sh
for name in SECRET_NAME_ONE SECRET_NAME_TWO; do
  printf 'Value for %s (not shown): ' "$name"; read -rs value; echo
  printf '%s' "$value" | glab variable set "$name" --masked --protected -R GROUP/PROJECT
  unset value
done
```

Flags from `glab variable set --help`: `-m/--masked`, `-p/--protected`, `--hidden` (value cannot be
shown again), `-s/--scope ENVIRONMENT`, `-t/--type file` (File type: the job gets a path), `-r/--raw`
(no variable expansion), `-g/--group` (group-level), `-d/--description`.

Choose per secret: masked (value must be one line, no spaces, at least eight characters; if it
cannot be masked, prefer an external secrets manager or File type), protected (only protected
branches and tags see it; drop it if a merge request pipeline needs the value), hidden, and an
environment scope. `glab variable set` creates a new variable; replacing an existing one is
`glab variable update`. List first (`glab variable list -R GROUP/PROJECT`, names and settings
only) and show the user any name that already exists.

### 4. Protected branches and merge settings

See references/repo-settings.md for the API calls. One step per branch rule and one for the project
settings call.

### 5. Google Cloud trust

See references/gcp-wif-trust.md, steps 3 and 4: the provider and the service account binding are
separate steps. Show `gcloud config get-value project` first so the user can confirm the project.

### 6. Commit the translated pipeline

In a local clone of the GitLab project, on a branch:

```sh
glab repo clone GROUP/PROJECT
cd PROJECT && git switch -c migrate/gitlab-ci
# write .gitlab-ci.yml here (reviewed with the user first)
git add .gitlab-ci.yml
git commit -m "ci: add GitLab CI pipeline translated from GitHub Actions"
git push -u origin migrate/gitlab-ci
glab mr create --fill --target-branch main --yes
```

Show `git diff --cached` before the commit. The commit, the push and the merge request are
three writes; ask for the go once for the group when the user says so, and show the merge request
URL after.

### 7. Webhooks, Slack, runners

Webhook: see references/repo-settings.md (the `token` goes in by stdin). The GitLab for Slack app and
runner registration are UI steps; give the user the settings path and wait for them to report back.

### 8. Mirror

See references/cutover-and-rollback.md. Credentials are entered in the GitLab UI by the user.

### 9. Remotes

Local clones only. See references/cutover-and-rollback.md ("Updating clones and submodules").

### 10. Archive the GitHub repository

See the next section.

## Steps that need a second confirmation

These cannot be undone cheaply or reach outside the new project. After the first go, show the exact
command and ask the user to reply with the confirmation phrase. Run only on that reply.

| Step | Command (draft) | Confirmation phrase |
|---|---|---|
| Archive the GitHub repository | `gh repo archive OWNER/NAME` | `archive OWNER/NAME` |
| Remove the GitHub identity binding | `gcloud iam service-accounts remove-iam-policy-binding ...` | `remove github binding` |
| Delete the GitHub provider | `gcloud iam workload-identity-pools providers delete ...` | `delete github provider` |
| Replace an existing GitLab variable | `glab variable update NAME ...` | `overwrite NAME` |
| Any other deletion | Not drafted by this skill | The user runs it themselves |

Do not pass `--yes` or other flags that skip a tool's own prompt.
