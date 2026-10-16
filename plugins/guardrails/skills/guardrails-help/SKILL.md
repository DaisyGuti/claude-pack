---
name: guardrails-help
description: Explains the guardrails hooks that block risky commands and file writes, why each rule exists, how to read the block log, and how a person runs a blocked command on purpose or turns one rule off for a repo. Use when a tool call fails with a "guardrails[...]" message, when asked what guardrails blocks or why, how to allow a blocked action, which rules are on, or what was blocked recently, even if the user does not name the plugin.
user-invocable: true
---

# Guardrails help

The `guardrails` plugin runs a hook before every Bash command, file write and file read. The hook
refuses risky actions with exit code 2 and a one-line message that starts with
`guardrails[<rule-id>]`. A person decides whether a refused action ever runs; Claude does not.

## If a call was just blocked

1. Stop. Tell the user in one or two sentences what was blocked and why, using the rule's reason.
2. Do the safe path named after "Instead" in the message when it matches what the user wants. For
   a protected branch that means: push a feature branch, then open a pull request (`gh pr create`)
   or merge request (`glab mr create`).
3. Do not retry the same goal in another form: different flags, `sh -c`, a script file, a split
   command, a variable. That is the evasion the rules exist to stop.
4. Never write to `.claude/guardrails-allow.txt`, the plugin files, or hook settings. The
   `guardrails-tamper` rule blocks it, and only a person may change them.

## Show the rules

Run this and present the output as a short table of rule id, what it blocks, why, and the safe
alternative. The script is the source of truth for the list, so do not answer from memory.

```sh
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/guardrails.py" --list-rules
```

## Show recent blocks

```sh
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/guardrails.py" --recent 20 --data-dir "${CLAUDE_PLUGIN_DATA}"
```

Each line is JSON with `ts`, `event`, `rules`, `tool`, `cwd`, `session` and the `command` (with
credential-shaped text replaced by `[redacted]`). `event` is `block`, or `allowed-by-config` when
the repo's allowlist let a rule through. Summarize repeats by rule so the user sees patterns.

## Read-only agents

Some agents are defined as read-only (the `core:reviewer` and `security:security-auditor` agents,
and any others in `READ_ONLY_AGENTS` in the script). A plugin agent cannot carry its own
permission mode, so the `read-only-agent` rule enforces it: when a call comes from one of them,
Write, Edit, MultiEdit and NotebookEdit are refused, and Bash is limited to a list of read-only
commands (`git diff`/`log`/`show`, `gh pr diff`, `glab mr diff`, `cat`, `grep`, `find` without
actions, the scanners). A report or scan result may be written under `$TMPDIR` only. Anything
that changes the repository, the remote, files or cloud state is refused. A read-only agent that
hits the rule should say in its report what change it would have made and stop.

The main session is never affected by this rule. To let a reviewer run a command the list does
not cover, a person adds `read-only-agent` to the allowlist for that repo (it turns the rule off
for every read-only agent there) or adds the command to the script in a pull request.

## How a person runs a blocked command on purpose

Hooks fire only when Claude calls a tool, so a person has three routes:

1. **One time:** type `!` and the command at the Claude Code prompt. Shell mode runs it directly,
   without going through Claude, so no hook fires. A separate terminal works the same way.
2. **A repo that needs a rule off:** a person creates `.claude/guardrails-allow.txt` in the
   project, with one rule id per line and `#` for comments:

   ```text
   # the docs bucket is public on purpose (reviewed in PR 123)
   gcp-public-access
   ```

   Use a text editor or their own terminal, never Claude. The file applies to everyone who works
   in that repo, so it belongs in a pull request or merge request. Unknown ids are ignored, so a
   typo leaves the rule on. `guardrails-tamper` and `cannot-decide` cannot be listed.
3. **Switch the plugin off:** `claude plugin disable guardrails@claude-pack` in a terminal.

Nothing a command or an environment variable says can turn a rule off. Only that file can.

## What the rules do not see

State these limits plainly when a user asks whether something is covered:

- The text of a script file that a command runs, shell aliases, and values held in variables
  that a command computes (`$(some-tool)`), except the current branch and variables set earlier
  on the same command line.
- Programs that start other programs themselves, and encoded or obfuscated commands.
- A search over a whole directory (`grep -r`, the Grep tool on a folder) that reaches a `.env`
  file. Only a call that names the secret file is blocked.
- Files added to the prompt with `@file`, which Claude Code inserts without a tool call. Setting
  `CLAUDE_CODE_DISABLE_FILE_MENTIONS=1` (Claude Code 2.1.299 or later, user or managed settings)
  makes those go through the Read tool, where the hook sees them.
- The PowerShell tool and MCP tools. The hook matches Bash, Write, Edit, MultiEdit,
  NotebookEdit, Read and Grep.

Keeping `security-guidance` installed alongside covers insecure code patterns; this plugin only
blocks.

## Failure behavior

The hook fails closed. Malformed input, a crash, or a timeout refuses the call, and the hook
entry sets `onFailure: "block"` so Claude Code itself blocks when the script cannot start. Python
3 must be on the PATH as `python3`. If the guard breaks, Bash and file edits stop until a person
fixes the install or disables the plugin; tell the user rather than working around it.

## Writing tests for code that handles credentials

The content rules also see test files. Build fake tokens from pieces at run time (for example
`"gh" + "p_" + "a" * 36`) so the file holds no literal that looks like a real credential.

For the facts behind each rule, with sources, see
[references/rule-sources.md](references/rule-sources.md).
