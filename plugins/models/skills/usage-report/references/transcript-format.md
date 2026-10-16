# Transcript format and price table

## Contents

- Where transcripts live (documented)
- Fields the script reads (observed)
- How the script counts
- The price table
- What the estimate leaves out

## Where transcripts live (documented)

From https://code.claude.com/docs/en/claude-directory (Application data), read 2026-10-16:

| Path | Contents |
|---|---|
| `~/.claude/projects/<project>/<session>.jsonl` | Full conversation transcript: every message, tool call and tool result |
| `~/.claude/projects/<project>/<session>/subagents/` | Subagent conversation transcripts, removed with the parent transcript when it ages out |
| `~/.claude/projects/<project>/<session>.orphaned-<timestamp>-<suffix>.jsonl` | A previous transcript set aside; not shown in the session picker |

`<project>` is the working directory path with separators replaced by hyphens. Files older than
`cleanupPeriodDays` (30 days by default, minimum 1) are deleted at startup. `CLAUDE_CONFIG_DIR`
moves the whole `.claude` folder when set. The transcripts are plaintext and can hold secrets
that passed through a tool; the script prints only counts and labels.

## Fields the script reads (observed)

The documentation names the files and not the fields inside each line. The script reads these,
observed on Claude Code 2.1.287, and skips any line it cannot parse:

- `type == "assistant"` lines, with `message.id`, `message.model`, `message.usage`,
  `message.content[]` (blocks of `type == "tool_use"` carry `id` and `name`), and `timestamp`.
- `message.usage`: `input_tokens`, `output_tokens`, `cache_read_input_tokens`,
  `cache_creation_input_tokens`, and when present `cache_creation.ephemeral_5m_input_tokens`,
  `cache_creation.ephemeral_1h_input_tokens` and `output_tokens_details.thinking_tokens`.
  Thinking tokens are part of `output_tokens`.
- `<agent-id>.meta.json` beside each subagent transcript: `agentType`, `description`, `model`
  (what was requested, such as an alias).

If a later Claude Code version renames a field, the symptom is zero responses or zero cost with
files read. Check the field names against a transcript line and update `read_usage` and
`absorb` in the script.

## How the script counts

- One API response is written as several lines, one per content block, all with the same
  `message.id`. The script merges them: tool names are collected from every line, and the usage
  of the line with the largest `output_tokens` is kept, since only the last line carries the
  final output count.
- A resumed session can replay earlier lines into a new file. The script counts each
  `message.id` once across all files.
- `<synthetic>` models (local placeholders) are skipped.
- A subagent run is one transcript file under `subagents/`. A run is flagged when its dominant
  model is in tier `top` or `frontier`, it used no Edit, Write, NotebookEdit or MultiEdit,
  spawned no Agent or Task, and wrote at most `--mech-output-max` output tokens (8000 by
  default). These are heuristics for finding leads. A person confirms each one.

## The price table

`scripts/prices.json` holds `as_of`, `source`, `reference_models` (the mid and small models
used for the "would cost about" estimate) and a `models` list. Each entry has:

- `match`: a model id prefix. The longest matching prefix wins. Partner ids such as
  `us.anthropic.claude-opus-5-5-v1:0` and `claude-haiku-4-5@20251001` are reduced to the part
  starting at `claude-` first.
- `tier`: `small`, `mid`, `top` or `frontier`, used for the flag.
- `input`, `cache_write_5m`, `cache_write_1h`, `cache_read`, `output`: USD per million tokens.
- Optional `long_prompt_tokens` and `long`: a second set of rates applied to a request whose
  prompt (input plus cache reads and writes) is over the threshold.

The source is https://platform.claude.com/docs/en/about-claude/pricing. To refresh, fetch the
page, copy the table into the same shape, set `as_of` to the fetch date, and pass the file with
`--prices`. A model with no matching entry is listed in the warnings and costs $0 in the totals.

## What the estimate leaves out

- Fast-mode, data-residency (`inference_geo`) and batch multipliers.
- The usage-credit versus included-allowance split on subscription plans.
- Contracted rates. Claude Code can apply a `modelPricing` managed setting to its own figure;
  this script uses list price.
- Usage from other machines, claude.ai chat, or sessions whose transcripts have aged out.
