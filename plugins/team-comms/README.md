# team-comms

Slack catch-ups and drafts, standups and weekly updates, design docs and decision records.

## What it carries

| Skill | Use it to |
| --- | --- |
| `slack-catchup` | Summarize channels, threads and DMs since a time into decisions, asks of you, blockers and FYIs, with links and time-sensitive items flagged. Read-only. |
| `slack-draft` | Draft a message or thread reply: answer a question, ask for help, request a PR or MR review, post a status or incident update, announce a release. Drafts only. |
| `slack-send` | Post, schedule or save as a Slack draft the text you approved, after one confirmation. Runs only when you type `/team-comms:slack-send`. |
| `status-update` | Build a standup or weekly update from your git commits, pull requests or merge requests and tickets on GitHub (`gh`) or GitLab (`glab`). |
| `design-doc` | Write an R&D design doc or RFC with a required security and compliance section, saved in the repo's docs folder. |
| `adr` | Write a numbered architecture decision record in MADR format, with superseded records linked. |

Skills show as `/team-comms:<skill>` and Claude also picks them up from what you ask.

## Install alongside

- **Slack plugin** (`/plugin install slack@claude-plugins-official`): the quickest way to
  connect Slack. It registers Slack's MCP server and signs you in. See
  [`docs/connect-slack.md`](docs/connect-slack.md) for every way to connect, and for what to
  ask a workspace admin to approve. Without Slack connected, the skills ask you to paste the
  text.
- **GitHub or GitLab integrations**, or the `gh` and `glab` command-line tools, for
  `status-update`. Check with `gh auth status` and `glab auth status`.

## Scripts

All scripts use the Python 3.11+ standard library.

| Script | Used by | Does |
| --- | --- | --- |
| `scripts/lint_draft.py` | every drafting skill | Flags contrast constructions, hype words, unfilled placeholders and pasted secrets |
| `scripts/slack_helpers.py` | `slack-catchup` | Resolves "since yesterday" to a Slack timestamp and builds message links |
| `scripts/collect_activity.py` | `status-update` | Gathers commits, pull or merge requests, reviews and tickets as JSON |
| `scripts/doc_tool.py` | `design-doc`, `adr` | Finds the docs folder, numbers files, edits ADR status, checks completeness |

## Tests and evals

```sh
uv run pytest tests/team-comms
uv run python scripts/validate.py team-comms
```

Eval cases are in `evals/`. Cases for `status-update`, `design-doc` and `adr` build a
throwaway repo, so run those with the scaffold and tool grants:

```sh
claude plugin eval plugins/team-comms --scaffold --allow-tools Bash Write Edit --max-cost-usd 5
```

The full suite spends subscription allowance. Run it before a release; run one case with
`--case <name> --runs 1` to check a change.
