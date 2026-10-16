# Mirror period, URL changes, cutover, rollback and archive

Sources read on 2026-10-16: repository mirroring https://docs.gitlab.com/user/project/repository/mirror/
(overview, push and pull pages), the importer page https://docs.gitlab.com/user/project/import/github/
(mirror section), and the help output of `glab` and `gh`. Fetch the mirror pages again before
drafting a mirror.

## Contents

- [Mirror period](#mirror-period)
- [Freeze rules](#freeze-rules)
- [Updating clones and submodules](#updating-clones-and-submodules)
- [URLs that change](#urls-that-change)
- [Cutover order](#cutover-order)
- [Rollback](#rollback)
- [Archiving the GitHub repository](#archiving-the-github-repository)
- [After the move](#after-the-move)

## Mirror period

What the mirror pages say:

- A **push mirror** copies a GitLab repository to another location. It is available in every tier.
  The pages describe it for the case "the canonical version of your project has migrated to
  GitLab": keep a copy at the old home.
- A **pull mirror** copies from another location into GitLab on a schedule. It needs Premium or
  Ultimate. It pulls about 30 minutes after the last pull; the UI and API can trigger an update
  sooner, within a minimum interval. If a branch diverges, GitLab stops updating that branch.
  Branches deleted upstream are not removed downstream, and items deleted downstream come back at
  the next pull. After repeated failures the mirror is marked as a hard failure and stops.
- **Bidirectional** mirroring exists and the page warns it can cause conflicts. Do not use it.
- A mirror carries Git data only (branches, tags, commits). It does not sync pull requests, issues
  or merge requests, which the importer page states for GitHub.

Choose by who is the source of truth:

| Situation | Setup | Tier |
|---|---|---|
| GitHub stays the source for a short bridge, GitLab follows | Pull mirror into GitLab | Premium, Ultimate |
| GitLab is the source from cutover, GitHub keeps a copy for consumers | Push mirror from GitLab | Any |
| Free tier and GitHub must stay the source for a while | A scheduled GitLab pipeline job that runs `git fetch` from GitHub and pushes, or repeat the one-time cutover quickly | Any |

Because issues and merge requests do not sync, the practical plan is:

1. Import (a point-in-time copy of everything).
2. Freeze creation of GitHub issues and pull requests from the import start. Anything created after
   is re-created by hand or lost on cutover day; say which in the plan.
3. Keep Git data in step if the import-to-cutover gap is long (pull mirror, or a push by hand).
4. At cutover, GitLab becomes the source. Optionally enable a push mirror to GitHub for consumers
   that still clone from there.
5. End the mirror on a written date. The skill does not pick a length: the right length is how
   long outside consumers (submodule users, package consumers, dependent pipelines) need to move.
   Ask the user for that date and put it on the checklist.

Mirror credentials: the push mirror to a private GitHub repository needs a GitHub token or an SSH
deploy key. `glab repo mirror` can take credentials inside the URL, which would put a secret in the
command line and shell history. Use the GitLab UI (Settings > Repository > Mirroring repositories)
and have the user enter the credential there, or use an SSH URL with a deploy key. Never ask for the
token in chat.

Drafted mirror command, URL without credentials (SSH form shown; SCP-style URLs are not supported
by GitLab mirroring, so write it as `ssh://`):

```sh
glab repo mirror GROUP/PROJECT --direction=push --url="ssh://git@github.com/OWNER/NAME.git" \
  --protected-branches-only
```

Run it after the user's go, then add the key in the UI. Flags are from `glab repo mirror --help`:
`--direction` (`pull` or `push`), `--url`, `--enabled`, `--allow-divergence`,
`--protected-branches-only`.

## Freeze rules

- From the import start, no new GitHub issues or pull requests (state the exception process).
- From the final sync, nobody pushes to GitHub. A commit pushed there makes that branch diverge
  from GitLab, and the push mirror then overwrites it or skips it depending on the "Keep
  divergent refs" option.
- Protect branches in GitLab only after one pipeline passes.
- Announce the window, the owner, and the rollback trigger before it starts.
- An archived GitHub repository rejects pushes, including the mirror's. End the mirror first,
  then archive.

## Updating clones and submodules

For each developer clone (a draft for the person to run; it changes only their local settings):

```sh
git remote -v
git remote set-url origin git@GITLAB_HOST:GROUP/PROJECT.git
git fetch origin --prune
git branch --set-upstream-to=origin/main main
```

`glab repo clone GROUP/PROJECT` makes a fresh clone with the configured protocol. For a fork
workflow, re-create forks in GitLab and point `upstream` at the new project.

Submodules: edit `.gitmodules` in the superproject for any submodule that moved, then
`git submodule sync --recursive` and `git submodule update --init --recursive`. A relative URL
(`../lib.git`) follows the superproject to the new host, which is the easiest fix for projects that
all move together.

Build servers, deploy hosts and any machine with a deploy key: list them, repoint each, and
create a GitLab deploy key or deploy token for them. Deploy keys are not imported.

## URLs that change

| Where | What to do |
|---|---|
| README, docs, CHANGELOG compare links | Replace `github.com/OWNER/NAME` with the new project URL; the inventory lists each file and line |
| CI status badges | Use the GitLab pipeline badge for the new project |
| Container images | `ghcr.io/OWNER/NAME` becomes `$CI_REGISTRY_IMAGE` (the project's registry); keep the old tags pullable until consumers move |
| Package registries | npm, Maven, NuGet and RubyGems packages from GitHub Packages need publishing to the GitLab package registry or another registry, and consumers need new registry config |
| Go modules | `module github.com/OWNER/NAME` in `go.mod` is part of every import path. Changing it edits all importers. Keeping the old path with a proxy or vanity import is a decision for the team |
| Pages sites | `OWNER.github.io` sites move to GitLab Pages; update the links and DNS |
| Raw file links | `raw.githubusercontent.com` URLs in scripts and docs change to the GitLab raw path |
| API clients | Calls to `api.github.com` for this repository become GitLab API calls |
| Webhook receivers | They get GitLab payloads |
| Issue and pull request links elsewhere | GitHub numbers do not equal GitLab numbers for pull requests (they become merge requests, with `!`) |

Leave a pointer behind: a draft for the user to approve, run just before the mirror starts or after
the mirror ends:

```sh
gh repo edit OWNER/NAME --description "Moved to https://GITLAB_HOST/GROUP/PROJECT" \
  --homepage "https://GITLAB_HOST/GROUP/PROJECT"
```

## Cutover order

Use the generated checklist as the working list. The order that matters:

1. Everything in the checklist before "Cutover day" is done and checked.
2. Announce the freeze. Merge or park open work.
3. Final sync (mirror update or final push). Compare the default branch SHA on both hosts.
4. Protect branches, turn on "Pipelines must succeed", turn on Code Owner approval.
5. Switch deploy triggers and credentials to GitLab (WIF provider already added).
6. Repoint remotes. A push from a fresh clone works.
7. Watch the first pipelines on the default branch.
8. Open the rollback window and note its end date.

## Rollback

Decide the trigger before cutover (for example, the first production deploy fails and the cause is
not fixed within an agreed time). Keep these until the window closes:

- The GitHub repository unarchived, Actions enabled, branch protection as it was.
- The GitHub Workload Identity provider and its service account binding.
- GitHub secrets in place.

Steps:

1. Freeze GitLab pushes (protect the branches with "No one" for push, or set the project read-only
   by archiving it in GitLab).
2. Bring GitHub up to date with GitLab. If a push mirror ran, GitHub is already current. Otherwise
   push the default branch and tags from a clean clone: `git push github main --tags` with a
   remote named `github` (a draft; show the diff of refs first and do not use `--force`).
3. Re-enable GitHub deploy triggers and credentials.
4. Repoint developer remotes back.
5. Record what exists only in GitLab (merge requests, issues, comments created after cutover) and
   decide how to carry it: export, copy by hand, or accept the loss.
6. Tell the team in the same channel as the cutover announcement.

## Archiving the GitHub repository

Archive only when the rollback window has closed and the mirror has ended. Archiving makes the
repository read-only; `gh repo unarchive` reverses it.

This step needs a SECOND explicit confirmation. After the first go, show the exact command and ask
the user to reply with the repository name in the form `archive OWNER/NAME`. Run it only on that
reply:

```sh
gh repo archive OWNER/NAME
```

Without `--yes`, `gh` asks its own confirmation as well. Do not add `--yes` on the user's behalf.

This skill never drafts a repository deletion, a secret deletion or a branch deletion on GitHub. If
the user wants one, they run it themselves.

## After the move

- Remove the GitHub provider from the Google Cloud pool (references/gcp-wif-trust.md, step 7).
- Revoke the GitHub token used for the import. Rotate secrets that passed through the move.
- Remove GitHub secrets and variables the repository no longer needs. The user does this in
  GitHub settings; the skill does not draft deletions.
- End the mirror on its date and delete the mirror credential.
- Close the migration checklist with the date and the person who did it.
