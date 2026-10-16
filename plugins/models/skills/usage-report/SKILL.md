---
name: usage-report
description: Reports Claude Code token use and estimated list-price cost across sessions, grouped by model, subagent type, project and session, from the local session transcripts, and flags subagent runs that used a top-tier model for work that looks mechanical. Use when asked how much has been used or spent, which model is burning tokens, what subagents are costing, whether Opus is running where Sonnet or Haiku would do, for a weekly cost report, or for usage by project, even if the user never mentions transcripts. For this session's total alone, point to the built-in /usage (aliases /cost and /stats); for an HTML report with cache and skill breakdowns, point to the session-report plugin.
argument-hint: '[7d | 24h | 30d | all | YYYY-MM-DD]'
allowed-tools: Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/usage_report.py *) Read WebFetch
---

# Usage report

Totals tokens and estimated cost from the transcripts Claude Code keeps on this machine, then
reads the result for waste. Claude runs the script and interprets its output; the script does
the counting.

## What the built-ins already cover

Say which of these answers the question before running anything, and run the script only for
what they do not cover:

- `/usage` (aliases `/cost`, `/stats`): the current session's cost by model, prompt-cache
  statistics, and on subscription plans an attribution breakdown of recent usage by skill,
  subagent, plugin and MCP server for the last 24 hours or 7 days.
- The official `session-report` plugin: an HTML report of tokens, cache hits, subagents,
  skills and expensive prompts. It shows tokens and no dollar figures or model tiers.
- `/skill-doctor`: what each skill costs in context and how often it is used.
- `/insights`: how the user works, with friction points and suggestions.

This skill adds cost across many sessions, per model, per subagent type, and a list of subagent
runs that look like candidates for a smaller model.

## Steps

1. **Pick the window** from the argument: `7d` (default), `24h`, `30d`, `all`, or a date. The
   transcripts only reach back as far as the retention setting (`cleanupPeriodDays`, 30 days by
   default); say so if the user asks for longer.

2. **Run the script.** It reads the transcripts and prices them from `scripts/prices.json`,
   next to the script. Standard library only; it needs `python3` 3.11 or later.

   ```sh
   python3 ${CLAUDE_SKILL_DIR}/scripts/usage_report.py --since 7d --top 10
   ```

   Add `--json` for the full structure, `--dir PATH` if the transcripts live elsewhere
   (`CLAUDE_CONFIG_DIR` is honored), and `--prices FILE` for a different price table. If the
   script exits 2, read its message: it names the missing directory or the bad option.

3. **Check the price table.** The output header shows the table's date, and a warning appears
   when it is old or when a model has no price. For a stale or missing price, fetch
   `https://platform.claude.com/docs/en/about-claude/pricing.md`, write a corrected copy of
   `prices.json` to a temporary file, and rerun with `--prices`. Never edit the file inside the
   installed plugin, because an update replaces it. The format is in
   [references/transcript-format.md](references/transcript-format.md).

4. **Confirm each flagged subagent run.** The script lists runs where a top-tier model edited
   nothing, spawned nothing and returned a short answer. That shape suggests mechanical work,
   and the list is a set of leads to confirm. For each one, read its description and tools:
   - Search, list, inventory, count, summarize: a real candidate. Recommend the smaller model
     and the setting that applies it (below).
   - Review, audit, design, security, root cause, a decision: judgment work. Keep the tier and
     say why.
   - Ran Bash: the commands may have changed files. Ask to see them before recommending a
     smaller model.

5. **Report in plain language**, in this order:
   1. One paragraph: the window, total estimated cost, which model and which subagent type
      account for most of it.
   2. A table of the top models and the top subagent types with calls, tokens and cost.
   3. The confirmed candidates, each with its estimated cost now and at the mid and small
      tier, and the one-line change to make. The estimate reuses the same tokens, and a
      different model may use a different number of tokens, so call it approximate.
   4. Other things the numbers show: a low cache-read share, one session that dominates, many
      small subagent runs that could be one.
   5. Caveats: these are list-price estimates and not a bill, a subscription plan does not
      charge per token, the data covers this machine only, and the price table's date.

## Applying a change

- Give the subagent definition a `model:` (and `effort:`) in its frontmatter, or pass `model` when
  invoking it. For an unset model the subagent inherits the session's. Details and the
  resolution order are in the `model-recommender` skill's Claude Code settings reference.
- To judge which tier a recurring task needs, run the `model-recommender` skill on it.

## Privacy

The output contains project folder names and the short descriptions written for subagents.
Keep the report on this machine unless the user chooses to share it. The script never prints
prompt or response text, and the skill must not open transcript files directly to quote them.
