---
name: prompt-optimizer
description: Rewrites a prompt for Claude (system prompt, agent or skill instructions, API prompt, or a task prompt for a coding session) against Anthropic's current prompt-engineering guidance, then names the Claude model and effort that should run it and which parts can run in parallel. Use when someone asks to optimize, improve, tighten, review, debug or "fix" a prompt, asks why Claude ignores or over-applies an instruction, wants a better system prompt, wants a prompt that costs less, or pastes a prompt and asks how to run it, even if they never say "optimize". Out of scope: auditing a whole repository of prompts and agent files for outdated patterns (use the claude-api skill's prompt-audit) and picking a model when there is no prompt to rewrite (use model-recommender).
argument-hint: '[--file PATH] [--context "..."] [--model MODEL_ID]'
allowed-tools: Read WebFetch
---

# Prompt optimizer

Rewrite one prompt so Claude follows it reliably, then say how to run it. The guidance changes
with each model release, so fetch it at run time (step 2). Never rely on remembered model
behavior.

Inputs from `$ARGUMENTS`: `--file PATH` (the prompt), `--context "..."` (audience, use case,
one-shot or repeated workflow, tone to keep), `--model MODEL_ID` (the Claude model that will
run the prompt). With no `--file`, the text after the flags is the prompt.

## Steps

1. **Classify the input.**
   - Valid prompt (instructions aimed at a language model): continue.
   - Empty: ask the user to paste the prompt or pass `--file`, and stop.
   - Not a prompt (data, a bare question, a spec): say what it looks like and ask whether to
     write a prompt from it.
   - Several prompts: list them and ask which one. Do not merge them.
   - Prompt mixed with notes or critique: extract the prompt, state that assumption, continue.
   - Written for a model that is not Claude: say so, apply only the model-neutral checks
     (clarity, completeness, failure handling), and skip the Claude-specific ones.

2. **Pick the target model, then fetch its guidance.**
   - Use `--model`, a model named in the prompt or context, or else choose with the rule in
     "Which model and effort" below and say which you chose.
   - Fetch the hub page and the page for that model. URLs and what to look for are in
     [references/claude-guidance.md](references/claude-guidance.md). Read the model's own page
     first: effort defaults, instruction literalness, verbosity and tool-use habits differ per
     model, and they decide which fixes help.
   - If a fetch fails, say so, continue with the durable techniques in the reference file, and
     list "model-specific notes not checked" under Handoff items.

3. **Optimize, up to four rounds.** Each round: evaluate against
   [references/checklist.md](references/checklist.md), tag every issue P0 (breaks the prompt or
   causes wrong behavior), P1 (materially weakens output) or P2 (polish), then revise to fix
   every P0 and P1. Re-tag all open issues each round, since a P2 can become a P1 as the prompt
   changes. If unsure about severity, treat it as P1. Stop when only P2s remain.
   When criteria conflict, resolve in this order: intent preserved, correct, predictable,
   clear, robust, short. A revision may not grow the prompt unless it fixes a P0 or P1.

4. **Review adversarially, then finish.** Read the revised prompt through three lenses and note
   each P0 or P1 as `[P0|P1] issue: why it matters`:
   - a hostile tester (malformed input, contradictions, undefined edges),
   - a non-expert user (jargon, unclear placeholders, missing context),
   - a production engineer (nondeterminism, hidden state, prompt bloat, breakage on the next
     model release).
   Fix what turns up with one more revision. Anything still open goes under Unresolved issues.

5. **Report** in the format below. If the input is already good, return it unchanged with a
   one-line reason and "Total rounds: 0"; still give "How to run it".

## Which model and effort

Judge by the hardest decision the prompt demands.

| Work in the prompt | Tier | Effort to start with |
|---|---|---|
| Mechanical: extract, classify, convert, check against a crisp rubric, route | Smallest (Haiku class) | low or medium |
| Spec-driven implementation, research with citations, most verification, everyday agent work | Mid (Sonnet class) | medium, then high for harder or longer tasks |
| Hard judgment: architecture, novel analysis, a call that is costly to unwind | Top (Opus class) | high; xhigh only for long agentic coding |
| Work where the top tier at high effort still fails your checks | Highest (Fable class) | high |

Start at the cheapest tier that could work and move up one step after a weak result. Raise
effort before raising the tier. Look up the current model IDs, defaults and prices with the
`model-recommender` skill or the models overview; do not write IDs from memory.

## Parallel plan

Split the work into units. Two units run in parallel only when neither needs the other's output
and they do not write the same files. When the plan has parallelism, put an `<execution>` block
inside the final prompt so a fresh session fans out on its own, for example:

```text
<execution>
Stage 1, in parallel: (a) inventory the call sites, model sonnet, effort medium;
(b) fetch current deprecation dates, model haiku, effort low.
Stage 2, after both: write the findings, model opus, effort high.
Use a subagent only for independent work of real size; do the small steps directly.
</execution>
```

Give each unit its own model and effort; an unset model inherits the session's, which is
usually the most expensive. Mark a serial prompt plainly as "Serial: every step feeds the next".

## Report format

Output these sections in order, with no preamble. Write "None" for an empty section.

1. **Final version**: the optimized prompt in one block, ready to copy. No commentary inside.
2. **How to run it**: the model and effort with a one-clause reason, then the parallel plan as
   a table (stage, unit, model, effort, depends on), or "Serial".
3. **Iterations**: one line per round, then "Total rounds: N".
4. **Handoff items**: things to confirm by running the prompt on real inputs, only where you are
   unsure of a tradeoff.
5. **Unresolved issues**: open P0 and P1 items as `[P0|P1] issue: why`.

## Limits

- Never invent a Claude capability. Tool and feature names come from the fetched docs.
- Keep the user's intent and tone. Do not add scope, personas or rules they did not imply.
- The prompt's own text should carry no model release dates or version claims that will age.
