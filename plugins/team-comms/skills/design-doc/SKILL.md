---
name: design-doc
description: Writes an R&D design doc or RFC in the repo's docs folder - problem, goals and non-goals, options with tradeoffs, a recommendation, a required security and compliance section (data handled, trust boundaries, controls touched, gaps), rollout and open questions. Use when the user says "write a design doc", "RFC for", "propose how we should build", "compare approaches for", "write up the design", "tech spec", or wants to think through a technical choice before building, even if they do not say RFC. For recording one decision that is already made, use the adr skill instead.
argument-hint: "[title or one-line problem]"
---

# Design doc

The output is a markdown file in the repo's docs folder. The security and compliance
section is required, and it records evidence and gaps: the doc never says a design is
compliant or authorized, because a person with that authority decides.

## 1. Ground the doc in the repo

1. Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/doc_tool.py design locate`. It prints the
   folder in use (`docs/design`, `docs/rfcs` and similar, or the default to be created), and
   the numbering style. Follow the folder's existing conventions.
2. Read the code, docs and tickets the problem touches before asking questions. Read two
   existing design docs or ADRs if there are any, and match their depth and tone.
3. Ask the user only for what the repo cannot tell you: the real problem and who has it,
   the options they already considered, constraints (date, budget, platform), and who
   reviews. Ask them in one message.

## 2. Create the skeleton

`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/doc_tool.py design new "<title>"`

It prints the new file's path. The skeleton holds every required section with
`[TODO: ...]` markers. Fill it with the Edit tool. The structure and what each section
needs is in `${CLAUDE_SKILL_DIR}/references/section-guide.md`; read it before writing.

## 3. Fill every section

- **Problem**: what hurts, who it hurts, the evidence.
- **Goals** and **Non-goals**: outcomes a reviewer can check, and the things readers might
  expect that the work leaves out.
- **Options**: at least two real options plus "Do nothing". Each gets how it works, gains,
  costs and risks, and effort. Use facts from the repo; cite sources for outside facts.
- **Recommendation**: the option chosen, the two or three facts that decide it, and what
  would change the answer.
- **Security and compliance**: required. Follow
  `${CLAUDE_SKILL_DIR}/references/security-section.md` exactly. If the design handles no
  sensitive data, say so in each subsection with the reason; do not delete the subsection.
- **Rollout**: phases, flags, who is told, rollback, and the signal that shows success.
- **Open questions**: each with an owner.

Facts that go stale (versions, limits, prices, framework baselines) are looked up while
writing, from the named source, and stated with the source. Do not guess them.

Writing rules: plain, direct sentences. No hype words. Say what a thing is and stop; do not
add a contrasting "not X" clause. Define a term once and keep using it.

## 4. Check

1. `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/doc_tool.py design check <file>` lists missing or
   empty sections, fewer than two options, unfilled placeholders, a missing security
   subsection and any sentence that declares compliance. Fix and rerun until it prints `ok`.
2. `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/lint_draft.py <file>` checks style and secrets.
   Fix and rerun until it prints `clean`.

## 5. Report

Tell the user the file path, then three things: the recommendation in one sentence, the
open questions that need an answer before review, and what the security reviewer should
look at first. Do not commit unless asked. If the project has a security or
compliance plugin installed from this marketplace, suggest it for a deeper threat model
and link its output from the doc.
