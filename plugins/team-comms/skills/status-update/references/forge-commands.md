# What collect_activity.py runs on GitHub and GitLab

## Contents

- [Check the tools](#check-the-tools)
- [GitHub](#github)
- [GitLab](#gitlab)
- [Other trackers](#other-trackers)
- [Limits](#limits)

The script picks the host from the `origin` remote URL: a URL containing `gitlab` is
GitLab, one containing `github` is GitHub. A self-hosted server with another name needs
`--host github` or `--host gitlab`. Run the commands below by hand when a warning needs
diagnosing.

## Check the tools

| Tool | Installed? | Signed in? | Sign in |
| --- | --- | --- | --- |
| `git` | `git --version` | not needed | `git config user.email you@example.com` sets the author the script matches |
| `gh` | `gh --version` | `gh auth status` | `gh auth login` |
| `glab` | `glab --version` | `glab auth status` | `glab auth login` |

For a self-hosted GitLab, sign in with `glab auth login --hostname <host>`.

## GitHub

Run inside the repo. `@me` is the signed-in user.

| What | Command |
| --- | --- |
| Pull requests opened by the user | `gh pr list --author @me --state all --limit 100 --json number,title,state,url,updatedAt,mergedAt,isDraft,reviewDecision,headRefName` |
| Pull requests the user reviewed | `gh pr list --search "reviewed-by:@me -author:@me" --state all --limit 100 --json number,title,state,url,updatedAt` |
| Reviews waiting on the user | `gh pr list --search "review-requested:@me" --state open --limit 100 --json number,title,url,updatedAt` |
| Issues assigned to the user | `gh issue list --assignee @me --state all --limit 100 --json number,title,state,url,updatedAt,closedAt` |

The script keeps items whose `updatedAt` is inside the window. Waiting reviews are kept
whatever their age, because an old request still waits.

## GitLab

`glab` lists merge requests and issues for the project in the current directory.

| What | Command |
| --- | --- |
| Signed-in user | `glab api user` (the script reads `username`) |
| Merge requests opened by the user | `glab mr list --author <username> --all -F json --order updated_at -P 100` |
| Reviews waiting on the user | `glab mr list --reviewer <username> -F json -P 100` |
| Issues assigned to the user | `glab issue list --assignee <username> --all -O json --order updated_at -P 100` |

Merge request state `opened` is reported as `open`. The script does not collect reviews the
user finished on GitLab, and says so in `warnings`. Ask the user whether any belong in the
update.

## Other trackers

Jira, Linear and other trackers are not read. If the team tracks work there, ask the user
to paste the ticket titles and statuses, or the ticket keys named in branch names and
commit subjects, and fold them into the update with the same rules.

## Limits

- At most 100 items per list; a `warnings` entry says when a list hit the cap.
- Commits are matched by the author email and filtered by author date, on every local
  branch and remote-tracking branch. Fetch first (`git fetch --all`) to include teammates'
  pushes of the user's own branches.
- Only repos the user names (or the current one) are read. Work in another repo needs
  `--repo <path>`.
