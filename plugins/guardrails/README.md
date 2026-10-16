# guardrails

Hooks that block risky actions while Claude works on a government codebase. A rule that must hold
every time lives in a hook, because a skill is only advice Claude may skip.

One `PreToolUse` hook runs before Claude's Bash, Write, Edit, MultiEdit, NotebookEdit, Read and
Grep calls. It exits with code 2 and one line telling Claude what was blocked and what to do
instead. Run `/guardrails:guardrails-help` for the current list of rules with the reason for each,
or `python3 hooks/guardrails.py --list-rules` from this folder.

## What it covers

Protected-branch pushes (and force-pushes), skipped git hooks, downloaded code run unread, TLS
verification turned off, world-writable `chmod -R`, public GCP access, service account key
creation, privileged containers and Docker socket mounts, recursive deletes of `/`, the home
directory or the repository root, credentials written into files, and secret files read into the
conversation.

It parses commands the way a shell does (quotes, `&&`, pipes, `sh -c`, heredocs, `$(...)`), so
`echo "git push --force"` passes and `FOO=1 sudo bash -c 'git push -f origin main'` does not.

## Install notes

- Needs `python3` on the PATH (3.9 or newer; the script uses only the standard library).
- Needs Claude Code 2.1.295 or later for `onFailure: "block"`. On older versions the hook still
  blocks what it recognizes, but a crash or timeout lets the call through.
- The hook fails closed. If it breaks, Bash and file edits stop until the plugin is fixed or
  disabled (`claude plugin disable guardrails@claude-pack`).
- Pair it with `security-guidance` from the official marketplace, which warns on insecure code
  patterns after the fact. This plugin only blocks. `hookify` adds user-written rules.

## Running something it blocks

Hooks fire only on Claude's tool calls. A person types `!` and the command at the Claude Code
prompt, or runs it in a terminal. To turn a rule off for one repo, a person edits
`.claude/guardrails-allow.txt` (one rule id per line, `#` for comments) and commits it through a
pull or merge request. Claude cannot change that file; the `guardrails-tamper` rule blocks it.

## Block log

Each block appends a JSON line to `blocks.log` in the plugin data directory, with secrets
redacted. `/guardrails:guardrails-help` can show the recent ones.

## Limits

It reads what is on the command line. It does not see inside script files, aliases or computed
values, a search over a whole directory that reaches a `.env` file, `@file` mentions in a prompt,
the PowerShell tool, or MCP tools. Details and sources: `skills/guardrails-help/`.

## Tests

`uv run pytest tests/guardrails` from the repo root. Evals are in `evals/`; the `hooks-*` cases
need `--scaffold --allow-tools Bash` and a machine where Claude Code's Bash sandbox can start.
