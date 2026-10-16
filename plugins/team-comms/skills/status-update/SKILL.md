---
name: status-update
description: >-
  Builds a daily standup (yesterday, today, blockers) or a weekly update from the user's git
  commits, pull requests or merge requests, and tickets on GitHub (gh) or GitLab (glab),
  formatted for Slack. Use when the user asks for "my standup", "what did I do yesterday",
  "weekly update", "status for the team", "summarize my week", "what did I ship", or "update for
  Friday", even if they do not say Slack. Drafts the text only; posting is a separate step,
  /team-comms:slack-send. For a standup built from the user's own Slack messages, the Slack
  plugin's /slack:standup does that.
argument-hint: "[standup|weekly] [repo paths]"
---

# Status update

Every line of the update must trace to a commit, pull request, merge request or ticket in
the collected data, or to something the user says. Do not invent work, numbers, tickets or
blockers. This skill drafts text only and never posts.

## 1. Choose the kind and the window

- **Standup** (the default): window `last-workday`. Sections: Yesterday, Today, Blockers.
- **Weekly**: window `week`. Sections: Shipped, In progress, Next, Risks and asks.

If the user names a window ("since Monday"), pass a date: `--since YYYY-MM-DD`.

## 2. Collect the evidence

Run, once per repo the user works in (current directory if they name none):

`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/collect_activity.py --since <window> [--repo <path> ...]`

It reads git history on every branch for the user's commit email and, when `gh` or `glab`
is installed and signed in, their pull requests or merge requests, reviews and assigned
issues. It prints JSON. Read these fields:

- `commits`: the user's commits in the window.
- `authored`: pull or merge requests the user opened, with state and merge date.
- `reviewed`: reviews done in the window (GitHub only).
- `review_requested`: open requests waiting on the user.
- `issues`: assigned tickets updated in the window.
- `branch`, `uncommitted_files`, `unpushed_commits`: work in progress right now.
- `warnings`: what could not be read. Pass each warning to the user with its fix, for
  example "`gh` is not signed in; run `gh auth login`", and continue with what was read.

Exit code 2 means the input was unusable (not a repo, no git email). Relay the message. The
per-host commands the script runs, and the fields it reads, are in
`${CLAUDE_SKILL_DIR}/references/forge-commands.md`. Read it when a warning needs
explaining, or when the user's tickets live in a tracker other than GitHub or GitLab issues;
in that case ask the user to paste the ticket titles.

## 3. Turn evidence into outcomes

- Group commits under the pull or merge request that carries them, and describe the
  outcome in the request's words ("Added retries to uploads") and skip the commit-by-commit
  steps.
- Commits with no request: a branch in progress. Describe by branch and subject.
- Yesterday or Shipped: merged requests, closed issues, completed reviews, and commits
  that landed. Today or Next: open authored requests, assigned open issues, the current
  branch, and `review_requested` items. In progress: draft requests, unpushed commits,
  uncommitted files on a branch with recent commits.
- Blockers or Risks and asks: only what the data shows (a request with
  `review_decision` of `CHANGES_REQUESTED`, a review waiting for days, an issue
  the user flagged) plus anything the user tells you. If the data shows none, write "None
  that I can see" for a standup and ask the user "Anything blocking you that git would not
  show?" Never fill the section with guesses.
- Mark anything uncertain with `[confirm: ...]`.

Formats and examples are in `${CLAUDE_SKILL_DIR}/references/formats.md`. Read it before
writing.

## 4. Write and check

Keep a standup to about eight lines and a weekly update to one screen. Plain, direct
sentences. Links as plain URLs after the item. Names of other people appear only where the
data shows them (a reviewer, an author).

Writing rules: no hype words, and no contrasting "not X" clause after a claim. Say what the
thing is and stop.

Save the draft to a temporary file and run
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/lint_draft.py --allow-placeholders <file>`. Fix
findings and rerun until it prints `clean`. The flag lets `[confirm: ...]` markers through
so the user can see and fill them.

## 5. Show it

Print the draft in one block. Add one line on what it covered ("2 repos, since Tuesday
00:00, GitHub and git") and the warnings. Then: "Say `send` and I will hand this to
/team-comms:slack-send, or tell me what to change."
