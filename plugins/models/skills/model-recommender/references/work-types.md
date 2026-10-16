# Work types and the tier to start with

Tier names are relative: smallest (Haiku class), mid (Sonnet class), top (Opus class),
highest (Fable class). The current model in each class and its ID come from the models
overview fetched at run time.

## Contents

- Table of work types
- Signals to move up
- Signals to move down
- Patterns that waste tokens
- Sources

## Table of work types

| Work type | Examples | Start at | Effort to start | Check before trusting it |
|---|---|---|---|---|
| Mechanical | Extract fields, classify tickets, convert formats, list files that match a rule, summarize a short log, route a request | Smallest | low or medium | Exact match against 20 hand-labeled inputs |
| Implementation | Write a function to a spec, apply a refactor, write tests, fill a template from a design | Mid | medium; high for longer or harder tasks | Tests pass and the diff stays in scope |
| Verification | Run and read a test suite, check a diff against a checklist, review for a known list of problems | Mid | medium or high | It finds a known planted defect |
| Research with citations | Read several sources and report with links, compare vendor docs | Mid | high | Every claim traces to a source |
| Judgment | Architecture choices, security design, a root cause across a large system, a decision that is costly to reverse | Top | high; xhigh for long agentic coding | A reviewer who knows the answer agrees on a sample |
| High-volume or latency-bound | Chat replies, per-request routing, inline suggestions | Smallest, or mid at low effort | low or medium | Latency and cost per request on real traffic |
| Long-horizon agentic | Multi-hour coding or migration runs with many tool calls | Top | the effort page's recommendation for that model | Tests, a reviewable diff, and a spend cap |

## Signals to move up

- The check fails on real inputs after raising effort one level.
- Output is shallow on a task that needs several steps of reasoning (lower effort levels
  scope work to exactly what was asked).
- The unit makes a call that is costly to unwind (security design, data deletion plan,
  a customer-facing commitment).
- Errors from this unit surface only downstream, far from where they were made.

## Signals to move down

- The output is correct on every sample and the model finishes in a few calls.
- The unit only reads and reports (no edits, no decisions).
- The same unit runs many times per day, so a small saving repeats.
- A lower effort on the same model passes the same check.

## Patterns that waste tokens

- Running every unit on the session's model. Set the model per unit.
- Spawning a subagent for a lookup that one search answers.
- Giving a reading-only helper the top tier because the main session uses it.
- Building a multi-model cascade before sweeping effort on a single model. The cost-and-
  intelligence page advises tuning one model first, because a multi-model setup has to beat the
  single model's whole curve of quality against spend. Models also keep separate prompt
  caches, so a cascade gives up cache reuse.
- Treating the highest tier as the default for knowledge work that the top tier already passes.

## Sources

- Choosing a model: https://platform.claude.com/docs/en/about-claude/models/choosing-a-model
- Effort: https://platform.claude.com/docs/en/build-with-claude/effort
- Optimizing for cost and intelligence (advisor and orchestrator patterns): https://platform.claude.com/docs/en/about-claude/models/optimizing-for-cost-and-intelligence
- Manage costs in Claude Code (model choice, subagents): https://code.claude.com/docs/en/costs
- The table above is this pack's working rubric, read against those pages on 2026-10-16. The
  tier-to-work mapping is a starting point to verify on real inputs.
