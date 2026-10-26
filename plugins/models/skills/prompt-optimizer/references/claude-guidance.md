# Claude prompting guidance: where to fetch it and the durable techniques

## Contents

- Fetch these first
- What to look for on a model's page
- Durable techniques (stable across models)
- Prompt patterns that backfire on current models
- Sources

## Fetch these first

Use WebFetch with the `.md` suffix, which returns the raw page.

1. Hub: `https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices.md`.
   Its first section is a table that links one prompting page per model. Read that table, then
   open the row for the target model.
2. The model's own page, for example
   `https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-<model-slug>`
   with the slug taken from the hub table (the slug is the model name in lowercase with
   hyphens). Do not guess a slug; copy the link from the hub.
3. When the prompt will run through the API and the user has not chosen an effort, also fetch
   `https://platform.claude.com/docs/en/build-with-claude/effort.md` and read the
   recommendation for that model.

## What to look for on a model's page

The per-model pages exist because models differ. Check each of these and apply only what the
prompt's workload needs:

- Effort: the default level, which level the page recommends for coding, agentic, chat and
  high-volume work, and what happens at the low end (shallow reasoning, skipped checks).
- Literalness: whether the model applies an instruction only to the case named.
- Verbosity: whether visible length follows effort or has to be prompted.
- Verification: whether the model already checks its work, so an added "double-check"
  instruction costs tokens for nothing, or whether it needs the instruction.
- Tool use and subagents: how readily it calls tools and delegates, and the damping text the
  page suggests.
- Early stopping and check-ins on long tasks, and the text the page suggests for that.
- Progress updates, formatting and refusal behavior, when the prompt serves a product.

When the page offers sample prompt text for a symptom the user reports, quote that text into
the revision and cite the page.

## Durable techniques (stable across models)

These come from the hub page's general-principles section and apply to the prompt text itself.

- **Be clear and direct.** Test: show the prompt to a colleague with no context; if they would
  be confused, so will Claude. Say the output format, constraints and audience.
- **Explain why.** A rule with its reason generalizes better than a bare rule. Instead of
  "never use ellipses", write that the reply is read aloud by a speech engine that cannot
  pronounce them.
- **Use examples.** Three to five, relevant to the real use, varied enough to avoid a pattern
  the writer did not intend, each wrapped in `<example>` tags inside `<examples>`.
- **Use XML tags** when the prompt mixes instructions, context, examples and input. Keep tag
  names consistent and nest them when the content has a hierarchy.
- **Give a role** in the system prompt. One sentence helps.
- **Put long documents first and the question last.** Wrap each document with its source in
  tags. For long-document tasks, ask for the relevant quotes first, then the answer.
- **Say what to do.** "Write flowing prose paragraphs" works better than "do not use
  markdown". The prompt's own style tends to carry into the reply, so write the prompt in the
  style the reply should have.
- **State scope.** Current models follow instructions literally. If a rule applies to every
  section or every file, say "every", and name the cases.
- **Handle the failure cases in the prompt**: missing or empty input, ambiguous instructions,
  input in the wrong format. A bare "if unsure, say so" does not cover them.
- **Do not prefill.** Current Claude models reject a prefilled last assistant turn with an
  error; the hub page's migration section lists which. Use structured outputs, a direct
  instruction, or XML tags for the format.
- **Ask for action when you want action.** "Can you suggest changes" gets suggestions; "change
  this function" gets edits.
- **Parallel tool calls.** To push independent calls into one turn, tell the model to make all
  independent calls together and never to guess a parameter for a dependent call.
- **Subagents.** The hub offers damping text for over-delegation: delegate when work is parallel,
  needs isolated context or is an independent workstream; work directly for small, sequential or
  single-file tasks.

## Prompt patterns that backfire on current models

- Emphatic language ("CRITICAL", "you MUST", "ALWAYS use the tool", "if in doubt, use the
  tool") made earlier models pay attention. Current models over-apply it. Replace it with the
  normal phrasing "Use X when ..." and the reason.
- Vague flourishes ("think outside the box", "go above and beyond") add nothing. Replace them
  with the concrete behavior wanted. When more is wanted, ask for it by name.
- Blanket thoroughness instructions that were added to fight laziness on older models.
- Instructions that tell the model to write out its reasoning in the reply. Some models decline
  such requests. Ask for the answer plus a short explanation, and read reasoning from the
  thinking output where the API provides it.
- Verification boilerplate on models whose page says they already verify.
- Negative-only rules ("do not do X") with no positive description of what to do instead.

## Sources

- Prompting best practices (hub): https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices
- Effort: https://platform.claude.com/docs/en/build-with-claude/effort
- Models overview: https://platform.claude.com/docs/en/models/overview
- Claude Code tools reference ("Read tool behavior" covers PDFs, page ranges and the poppler
  requirement): https://code.claude.com/docs/en/tools-reference
- Techniques above were read from the hub page on 2026-10-16; the per-model pages are read at
  run time and are not summarized here, because they change with each release.
