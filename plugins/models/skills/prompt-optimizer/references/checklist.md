# Optimization checklist

Apply each item to the current version of the prompt. Tag every failure P0 (breaks the prompt or
causes wrong behavior), P1 (materially weakens output) or P2 (polish only). The techniques are
explained in [claude-guidance.md](claude-guidance.md); the model's own page decides which of
them matter for the workload.

## Contents

- Clarity and completeness
- Structure and format
- Failure handling
- Fit to the target model
- Extensibility (repeated workflows only)
- Over-engineering
- Severity examples

## Clarity and completeness

- The task, inputs, outputs and constraints are each stated once and do not conflict.
- The audience and the definition of a good result are explicit.
- Every rule that would surprise a newcomer carries its reason.
- Scope words are explicit: "every section", "only the files under src/", "stop after the
  report".
- Edge cases and stop conditions are defined: when the work is done, when to ask, what to do
  when a tool or source is unavailable.
- Large inputs (long PDFs, spreadsheets, whole standards or repos) go through an extraction
  step first: one prompt per document writes the relevant excerpts with their sources to a
  notes file, and the main prompt works from the notes (SKILL.md, "Prompts that name large
  documents"). One prompt that reads them all whole overflows its context.
- A chain runs from one paste: the main prompt holds the extraction prompts and its
  `<execution>` block starts them. Each extraction first records what its input actually is,
  has a fallback when a tool is missing, and stops to ask instead of guessing. A source the
  task needs but the user did not supply gets its own extraction when it is public, and a
  question to the user when it is not.
- The prompt does not rely on facts the model cannot know (today's date, private repo layout)
  unless it supplies them or a tool to get them.

## Structure and format

- Mixed content (instructions, context, examples, input) sits in separate XML tags with
  consistent names. A short single-purpose prompt needs no tags.
- Long reference material comes first and the question or task comes last.
- The output format is described by what to produce. For machine-read output the prompt asks for
  structured outputs or a schema, and does not depend on a prefilled reply.
- Two to five examples when the wanted behavior is hard to describe, covering an edge case,
  inside `<example>` tags.
- The prompt is written in the style the reply should have (plain prose in, plain prose out).

## Failure handling

The prompt itself says what to do for each of these, at minimum:

1. Missing or empty input.
2. An ambiguous instruction or request.
3. Input that does not match the expected format.

Add the model-specific ones from its page, for example what to do when a tool call is refused
or a long task runs out of room.

## Fit to the target model

- Effort and thinking are chosen on purpose and stated in "How to run it".
- Emphatic or defensive wording from older models is gone (see the backfire list in the
  guidance file).
- Instructions the model's page says it already follows are removed.
- Tool and subagent use is described the way the model's page recommends: when to use, not
  "always".
- The prompt asks only for capabilities Claude has. A cross-model comparison is a step for the
  user, since Claude cannot call another provider's API on its own.
- Anything the model's page lists as a known symptom of the workload (early stopping, skipped
  verification, silent long turns, scope growth) has its suggested text, and only if the prompt
  is exposed to that symptom.

## Extensibility (repeated workflows only)

Apply when `--context` says the prompt runs repeatedly or ships in a product.

- Inputs are placeholders with names and descriptions, so a script can fill them.
- The prompt keeps working when the model changes: no behavior depends on a quirk of one
  release, and any quirk workaround is labeled so it can be removed later.
- The output has a fixed shape that a downstream step can parse or a person can scan.
- An eval exists or the report says what a minimal one would check.

## Over-engineering

- No added personas, rules or sections the user did not imply.
- No duplicated instructions. Say it once, in the place it applies.
- No length growth unless it fixes a P0 or P1.

## Severity examples

- P0: two instructions contradict each other; the output format cannot be parsed by the step
  that consumes it; the prompt asks for a capability Claude lacks.
- P1: no handling for empty input; a rule with no scope on a model that applies rules
  literally; emphatic wording that causes the tool to be over-used; one prompt that has the
  model read several long documents whole; a chain the user has to start by hand; an
  extraction that assumes what an unopened input holds; a public source the task needs left
  as an open question.
- P2: wording polish, tag renaming, reordering without a behavior effect.
