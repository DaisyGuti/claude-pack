# Applying a model and effort recommendation in Claude Code

Read on 2026-10-16 from https://code.claude.com/docs/en/sub-agents (Choose a model),
https://code.claude.com/docs/en/commands, https://code.claude.com/docs/en/model-config and
https://code.claude.com/docs/en/skills. The model aliases (`opus`, `sonnet`, `haiku`, `fable`)
map to different model versions on different providers and change with releases; read the alias
table on the model-config page at run time. Re-fetch the page before quoting a setting name the user
will paste into a config file, since flags and variables are renamed between versions.

## Contents

- The main session
- Subagents
- Skills
- Where cost shows up afterward

## The main session

Ways to set the model: `/model` (a picker, or `/model <name>`; pressing `s` on a row switches
for the current session only), `claude --model <alias or ID>`, the `ANTHROPIC_MODEL`
environment variable, and the `model` key in a settings file.

Ways to set effort, highest priority first: the `CLAUDE_CODE_EFFORT_LEVEL` environment
variable, the `--effort` launch flag, `/effort` in the session (`low` to `xhigh`, `max`, `auto`;
`/effort status` prints it), a per-model level saved in settings, the top-level `effortLevel`
setting, then the model's own default.

## Subagents

In the subagent's frontmatter:

```yaml
---
name: file-scanner
description: Use proactively to list files that match a rule. Read-only.
tools: Read, Grep, Glob
model: haiku
effort: low
---
```

- `model` takes an alias (`sonnet`, `opus`, `haiku`, `fable`), a full model ID, or `inherit`.
- `effort` takes `low`, `medium`, `high`, `xhigh` or `max`, and overrides the session level.
- Resolution order for the model, first match wins: the per-invocation `model` parameter, the
  frontmatter `model`, the `CLAUDE_CODE_SUBAGENT_MODEL` environment variable, the main
  conversation's model.
- To run every subagent on one model, set `CLAUDE_CODE_SUBAGENT_MODEL` to the alias and
  `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1`; the forced value overrides frontmatter and
  per-invocation values, so use it as a cost brake and remove it when you want per-agent
  choices back.
- Built-in subagents: Explore follows the main conversation's model, Plan inherits it,
  general-purpose follows the order above. A session switched to a top-tier model therefore
  also moves subagents that inherit.
- Plugin-shipped agents can set `model`, `effort` and `maxTurns`. Set `maxTurns` as a cost
  guard on any agent that loops.

## Skills

A skill's frontmatter accepts `model` and `effort` for the turn the skill runs in. Use them for
a skill that is always mechanical (a lookup skill on `haiku`) or always hard.

## Where cost shows up afterward

- `/usage` (aliases `/cost` and `/stats`) shows the current session's cost estimate by model
  and, on subscription plans, an attribution breakdown by skill, subagent and plugin.
- The `usage-report` skill in this plugin totals several sessions by model and subagent and
  flags top-tier subagent runs that look mechanical.
