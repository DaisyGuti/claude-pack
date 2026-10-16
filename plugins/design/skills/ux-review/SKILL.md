---
name: ux-review
description: Judges an existing design for usability, accessibility and visual craft, and says what to change. Use when asked to review or critique a UI, screenshot, mockup, prototype, flow or component, to "roast" or grade a design, to explain why a page looks generic or AI-made, to check contrast, keyboard or reading-order risks from a design, or to answer whether a screen works for its user. Gives a readiness verdict and a ranked list of fixes with concrete values (label text, px size, hex). Judges what is shown; it does not build new UI (use frontend-design), review framework source line by line (use web-design-guidelines), or run live-page accessibility tests (use the accessibility plugin).
when_to_use: Also covers fast scored critiques ("grade this design in 60 seconds"), WCAG-minded design reviews of screenshots, and the usability pass on a design built with the U.S. Web Design System (load uswds as well).
---

# UX review

Three reference files hold the depth. This file is the router and the lens to reach for
first on an ordinary review. Parts of the references are adapted from phazurlabs/sumi
(Apache-2.0); see [LICENSE.txt](LICENSE.txt).

## First pass: what kind of review is this?

| Situation | Go to |
|---|---|
| An existing UI, screen, or flow: does it work, is it clear | Core UX lens below |
| Accessibility, WCAG, contrast, keyboard, screen reader, cognitive load | `${CLAUDE_SKILL_DIR}/references/accessibility.md` |
| Polished-looking UI code or "why does this look generic / AI-made" | `${CLAUDE_SKILL_DIR}/references/craft.md` |
| A fast, opinionated, scored pass: "roast this", "grade this design" | `${CLAUDE_SKILL_DIR}/references/critique-protocol.md` |
| Reviewing code (not a screenshot) for accessibility in depth | `${CLAUDE_SKILL_DIR}/references/accessibility.md`, section "Reviewing implementation code" |
| A broad implementation audit of real UI code: forms, focus, i18n, hydration, navigation state, dark mode, anti-patterns | the `web-design-guidelines` skill (Vercel's Web Interface Guidelines, fetched fresh) |
| The product uses the U.S. Web Design System | the `uswds` skill as well. Its tokens and components win over the numbers in `craft.md` |
| A live page or running dev server is reachable and the ask goes deeper than a code read: automated scan, keyboard and screen-reader pass, whole-site audit, fixes, regression diff | the `accessibility` plugin, which points to AccessLint's `accesslint:accessibility-*` skills. `accessibility.md`, section "Live and automated testing", says which one and how its findings are graded |

More than one applies often. Lead with whichever is closest to what was actually
asked, and pull in a second reference file rather than trying to make one file cover
everything.

## Core UX lens

Ask these first on an ordinary review of an existing screen or flow. They catch what costs a real user time, trust or a finished task, before any polish comment.

1. Who is the user, and what did they come here to do? Failing answer: the reviewer cannot say in one sentence, or the screen serves the team's goal and the user's goal is missing.
2. Is the main action obvious and within reach? Failing answer: two or more buttons carry equal weight, the action sits below the fold or behind a menu, or its label does not say what happens next.
3. What does the eye land on first, and is that the right thing? Failing answer: the first stop is a banner, a decoration or a secondary link while the content or action the user needs sits further down.
4. What must the user remember or work out that the screen could show? Failing answer: they carry a code, a price or a choice from an earlier step, or they guess what a field expects because no example or format is shown.
5. What happens when something goes wrong, when there is nothing yet, and while it loads? Failing answer: a blank area, a spinner with no end, an error that does not say what to change, or entered data lost after a failed submit.
6. Do the words match what the user would call things? Failing answer: internal names, product jargon or system terms in labels, or one thing called three different names across the flow.
7. What could be removed without loss? Failing answer: fields, steps, links or paragraphs that no user task needs, each one a place to stall or leave.

## Default output shape

The answer to an ordinary review has three parts. Start with one line on readiness. List the issues worst first. End with the single next step that would teach the most.

Readiness words:
- **Ready**: a real user can finish the main task, and the remaining issues are polish.
- **Nearly ready**: the task is finishable, and one or two issues will cost some users time or trust.
- **Needs work**: a common path stalls, misleads or fails, and the screen should change before release.
- **Rework**: the screen does not support the user's main task as built.

```markdown
**Readiness:** <Ready | Nearly ready | Needs work | Rework> - <one sentence on why>

**Issues, worst first**
1. <Where: screen, element or step>
   - What goes wrong for the user: <the time, trust or task lost>
   - Change: <concrete edit with real values, such as label text, px size, hex, field order>
2. ...

**Next step:** <the one user test, measurement or decision that would teach the most, and what result would change the plan>
```

List only issues that exist, and give each a real location. Where a value cannot be known from the evidence, say what to measure instead of guessing a number.

## When the input is a screenshot

Say plainly what a screenshot can and can't prove before making any accessibility or
interaction claim from it. `${CLAUDE_SKILL_DIR}/references/accessibility.md`, section
"What a screenshot can and cannot show", has the exact split: contrast risk and layout
are visible; keyboard order and ARIA are not. A guess about implementation, reported as a
finding, reads as verified when it never was, so label it unverified and name the check
that would settle it.

## Finishing the review

- Review what you were given. When the input is a path, an image or a URL, open it before
  you answer. When the ask does not say which kind of review it wants, use the Core UX lens
  and the default output shape, and say so in one line. Ask a question only when there is
  nothing at all to review.
- Take every question in the Core UX lens to an answer, or write "cannot tell from this
  input" beside the ones the evidence does not reach. A review that stops partway has
  skipped steps it announced.
- Open the reply with the readiness line (or the verdict, for a scored pass), then the
  issues, worst first. Give each change as a real value: label text, px size, hex.
- When the user asked only for a review, report and leave the files alone. When the
  user also asked for the fixes, make the edits and name the files changed.
