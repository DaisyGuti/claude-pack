---
name: model-recommender
description: Recommends which Claude model tier and effort level to use for a kind of work, such as a task, pipeline stage, agent, Claude Code subagent or product feature, using Anthropic's current lineup, prices and effort guidance fetched at run time. Use when asked "which model should I use", "Opus, Sonnet or Haiku", "what effort level", "is this model overkill for this", "which model for my subagents", "how do I cut model cost without losing quality", or when designing a multi-step workflow that mixes models, even if the user never says "recommend". Covers Claude models on the Claude API, Google Cloud and Amazon Bedrock. Out of scope: rewriting a prompt (use prompt-optimizer), reporting past spend (use usage-report) and auditing the model calls in a codebase (use model-usage-audit).
argument-hint: '[--file PATH] [--context "..."]'
allowed-tools: Read WebFetch
---

# Model recommender

Pick the cheapest Claude tier and effort that does the job, say how to check that it does, and
say what to change when it does not. The lineup, prices and defaults move with each release, so
read them from the docs at run time (step 2) and never from memory.

Input: a description of the work, or `--file PATH` to a prompt or plan. `--context "..."` can
add volume, latency needs, where it runs and how sensitive the data is. If the work is too
vague to classify, ask one question.

## Steps

1. **Split the work into units and classify each.** A unit is a piece that could run on its own
   model. Use the types in [references/work-types.md](references/work-types.md): mechanical,
   implementation, verification, research, judgment, high-volume or latency-bound, and
   long-horizon agentic. One request that mixes types becomes several units.

2. **Fetch the current lineup.** WebFetch these and read them before recommending anything:
   - `https://platform.claude.com/docs/en/models/overview.md`: current model IDs, the ID on the
     user's platform (Claude API, Google Cloud, Amazon Bedrock), prices, default effort,
     context window, retirement dates.
   - `https://platform.claude.com/docs/en/about-claude/models/choosing-a-model.md`: the two
     documented starting strategies and the selection matrix.
   - `https://platform.claude.com/docs/en/build-with-claude/effort.md`: the recommended effort
     per model, which differs by model.
   If any fetch fails, say which and what the recommendation therefore leaves unchecked.

3. **Choose tier and effort per unit.** Apply the rules below, then cross-check the choice
   against the fetched effort page for that model.

4. **Say how to verify.** A recommendation is a hypothesis. For each unit give a small sample
   of real inputs to run at the proposed setting, the pass check, and the escalation step if it
   fails. For recurring workloads, point to the `usage-report` skill to see what the setting
   costs afterward.

5. **Say how to apply it.** For Claude Code, give the exact setting for each unit from
   [references/claude-code-settings.md](references/claude-code-settings.md). For the API, give
   the model ID for the user's platform and the `output_config.effort` value.

## Rules

- **Start cheap and move up on evidence.** Smallest tier for mechanical work, mid tier for
  implementation and most verification, top tier for genuinely hard judgment. Move up one step
  after a weak result on real inputs.
- **Raise effort before raising the tier.** The effort docs describe effort as a lever within
  one model; a mid-tier model at higher effort often closes the gap that tempts people to jump
  tiers. Raise the tier when a higher effort still fails the check.
- **Reserve the highest tier for what the top tier cannot do.** The docs point to it for demanding
  reasoning and long-horizon agentic work, after evals at high effort on the next tier down
  fall short.
- **Subagents get their own model.** An unset subagent model inherits the session's, so a
  session on a top-tier model quietly runs every helper there. Name the model for each
  subagent. Spawn a subagent only for independent work of real size, because each one adds its
  own requests on top of the main conversation.
- **Effort has a floor.** Some models skip checks or stop early at the lowest levels on long
  agent tasks; the effort and per-model prompting pages say which. Keep low effort for short,
  scoped, non-judgment work.
- **Combine models only after one model's effort has been swept.** The cost-and-intelligence
  page describes a smaller executor that escalates hard decisions (serial work
  that is hard in spots) and a top-tier orchestrator that hands bulk work to cheaper workers
  (fan-out across independent files or cases). Recommend one only when the single-model curve
  of quality against spend leaves room for it, and say what to measure.
- **Stay inside Claude.** This skill compares Claude tiers. For a task Claude cannot do (image
  or video generation, speech) or a request to compare other providers, say so and stop.
- **Check what each model cannot do** before recommending a setting: some models reject
  disabling thinking, forced tool choice or sampling parameters. The model's migration notes
  in the overview list these.
- **Do not quote prices from memory.** Quote the fetched table with its date.

## Output

One table, then short notes. Use exactly these columns:

| Unit | Work type | Model (ID on your platform) | Effort | Why this tier | Move up if |
|---|---|---|---|---|---|

Then:
- **Cost note**: input and output price per million tokens for each model used, from the
  fetched table, and the relative cost of the plan against running every unit on the top tier.
- **How to verify**: the sample, the pass check and the escalation step per unit.
- **How to apply**: the Claude Code settings or API fields.
- **Not checked**: anything a failed fetch or missing information left open.

If the user supplied volume, estimate monthly cost as tokens times price and show the
arithmetic with its assumptions; otherwise skip the estimate.
