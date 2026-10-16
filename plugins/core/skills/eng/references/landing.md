# Landing a change: per-host commands

Every change lands as a pull request (GitHub) or merge request (GitLab) into the default
branch. Nothing is committed or pushed to the default branch, even where the repo's
instruction files allow it. Sources: GitHub CLI manual, `gh pr create`
(<https://cli.github.com/manual/gh_pr_create>), and GitLab CLI documentation,
`glab mr create` (<https://docs.gitlab.com/cli/mr/create/>), both read 2026-10-16.
Re-read the page when a flag below is rejected.

## Contents

- Find the host and the default branch
- Branch and commit
- Open the review on GitHub
- Open the review on GitLab
- When the review cannot be opened

## Find the host and the default branch

```sh
git remote get-url origin                       # github.com or a GitLab host decides the CLI
git symbolic-ref --short refs/remotes/origin/HEAD   # prints origin/<default-branch>
```

When `origin/HEAD` is unset, `gh repo view --json defaultBranchRef --jq .defaultBranchRef.name`
on GitHub and `glab repo view` on GitLab name the default branch. A self-hosted GitLab
host does not contain the word "gitlab" in every case; when the host is unclear, check
which CLI is signed in (`gh auth status`, `glab auth status`) and ask the caller.

## Branch and commit

```sh
git fetch origin
git worktree add ../<repo>-<branch> -b <type>/<short-name> origin/<default-branch>
```

- Name the branch for the change (`fix/export-duplicate-rows`). Make it in a separate
  worktree whenever `git status --short` lists paths you did not touch, and work there
  from the start.
- Stage by path (`git add <path> ...`), then run `git status --short` and confirm every
  staged path is yours. Never `git add -A`, `git add .` or `git commit -a`.
- Never stash, `git checkout -- <path>`, `git reset --hard` or `git clean` in a tree
  someone else may be using. Never amend, rebase a shared tree, or force-push unless the
  caller asked.
- Follow the repo's commit style; Conventional Commits (`fix(api): ...`) when the repo
  states none. Never bypass hooks (`--no-verify`) or signing. If the repo signs commits
  and signing fails, stop and report the error.

## Open the review on GitHub

Only after the caller or the repo's CLAUDE.md asked for it, and after the full gates
passed on exactly what you push.

```sh
git push -u origin <branch>
gh pr create --base <default-branch> --head <branch> --title "<title>" --body-file <file>
```

Use `--template <file>` or fill the repo's pull request template when it has one. Add
`--draft` when the caller wants a draft. Never merge it yourself.

## Open the review on GitLab

```sh
git push -u origin <branch>
glab mr create --source-branch <branch> --target-branch <default-branch> \
  --title "<title>" --description-file <file> --yes
```

Fill the repo's merge request template when it has one (`.gitlab/merge_request_templates/`).
Add `--draft` for a draft. Never merge it yourself.

## When the review cannot be opened

No remote, an unknown host, a CLI that is missing or signed out, or no instruction to
open one: leave the commit on the branch, and put in the report the branch name, the exact
push and create commands above with the values filled in, and the drafted title and body.
Retry a transient network failure twice, then stop and report.
