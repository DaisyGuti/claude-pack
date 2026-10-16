# Scored critique protocol

Adapted from phazurlabs/sumi's `roast` command and its Liz Lerman critique material
(Apache-2.0, https://github.com/phazurlabs/sumi). Modified: condensed, reordered and
reworded; see [../LICENSE.txt](../LICENSE.txt). Use this when the ask is for a
fast, opinionated, scored pass rather than the open-ended Core UX lens in `SKILL.md`:
"roast this," "grade this," "what's wrong with this in the next 60 seconds."

## Contents

- [Step 1 — statements of meaning, before any criticism](#step-1--statements-of-meaning-before-any-criticism)
- [Step 2 — questions before opinions](#step-2--questions-before-opinions)
- [Step 3 — score 10 dimensions](#step-3--score-10-dimensions)
- [Step 4 — classify every finding](#step-4--classify-every-finding)
- [Step 5 — top 3 strengths to keep](#step-5--top-3-strengths-to-keep)
- [Step 6 — one-line verdict](#step-6--one-line-verdict)
- [Output shape](#output-shape)
- [Quality bar](#quality-bar)

## Step 1 — statements of meaning, before any criticism

List 3–5 strengths with specific reasoning: what stands out and why, what
design decisions show clear intentionality, what would be lost if this got redesigned
carelessly. This identifies what to protect during iteration,
and it is the first step of the Liz Lerman Critical Response Process for a reason: a
critique that starts with judgment reads as a reaction.

## Step 2 — questions before opinions

Liz Lerman's process doesn't go from strengths straight to judgment; two rounds of
questions sit in between, and they're what keeps a critique from becoming an opinion
dump.

**The designer's questions** — if a designer is present, ask what they want examined
and answer that first. If none is present (the usual case for code or a screenshot),
infer the two or three decisions that were clearly deliberate and state what they
appear to be optimizing for. Naming an intention before judging it is what separates
a critique from a reaction.

**Neutral questions** — ask about the design without smuggling an opinion into the
question. A neutral question has no preferred answer.

- Neutral: "What decides which of these two actions is primary?"
- Not neutral: "Why is the primary action so hard to find?"

The second one is an opinion wearing a question mark. If a question can only be
answered by agreeing with the critic, either rewrite it as a real question or move it
into the findings where it belongs. When a neutral question exposes a decision with
no answer at all, that's usually a good finding on its own.

## Step 3 — score 10 dimensions

Score each 1–10. Be honest: most production work scores 4–7. An 8+ is
impressive; a 3 or below means a fundamental problem.

| # | Dimension | Measures |
|---|---|---|
| 1 | Clarity | Can users understand what to do without instruction? |
| 2 | Hierarchy | Is information prioritized visually and structurally? |
| 3 | Consistency | Does it follow established patterns and its own conventions? |
| 4 | Spacing | Is whitespace used on purpose? |
| 5 | Color | Harmonious, semantic, and accessible? |
| 6 | Typography | Clear, readable, hierarchical? |
| 7 | Interaction | Do interactive elements give clear feedback? |
| 8 | Accessibility | Does it work for users of all abilities? (the accessibility pass in `SKILL.md`'s routing table covers it in full) |
| 9 | Innovation | Does it solve the problem in a novel, valuable way — or borrow a trend without knowing why it worked? |
| 10 | Polish | Is craft quality and attention to edge cases high? |

A few of the checks worth citing directly when scoring:

- **Clarity** — the primary action is immediately identifiable; empty states say what
  to do next rather than just "nothing here"; no moment forces the user to guess what a
  button or link does. (Krug's "Don't make me think" — if the user has to think,
  clarity has failed.)
- **Hierarchy** — one primary action dominates visually per screen; size, weight,
  color, and position all reinforce the same priority order. (Von Restorff — the
  distinct item gets remembered; if everything is distinct, nothing is.)
- **Consistency** — the same action looks the same everywhere; platform conventions
  are respected. (Jakob's Law — users spend most of their time on *other* products
  and expect this one to behave the same way.)
- **Spacing** — a consistent scale (4, 8, 12, 16, 24, 32...); related items sit closer
  than unrelated ones. (Proximity is the strongest Gestalt grouping cue — spacing
  *is* meaning.)
- **Color** — roughly 60-30-10 distribution; semantic colors stay consistent (red
  always means destructive and never doubles as a warning); at most 5–6 distinct hues
  excluding neutrals.
- **Typography** — at most two font families; a real type scale (ratios like 1.2,
  1.25, 1.333, 1.5, 1.618); body ≥16px with line-height ≥1.5; line length 45–75
  characters.
- **Interaction** — every interactive element has hover, focus, and active states;
  feedback lands under 400ms or the user's attention breaks (the Doherty Threshold);
  loading states appear for anything over ~300ms.
- **Polish** — every state implemented (default, hover, focus, active, disabled,
  loading, error, empty); pixel-aligned; edge cases (long text, empty data, slow
  connections) handled rather than assumed away.

### Total and grade

Sum the 10 (out of 100): A 90–100, A- 85–89, B+ 80–84, B 75–79, B- 70–74, C+ 65–69,
C 60–64, C- 55–59, D 45–54, F 0–44.

### A quick "does this look AI-generated" check, worth running alongside the score

- Default Tailwind indigo/purple as the primary color, or a purple/indigo gradient on
  a near-white background — the single most common AI-generated tell.
  Inter/Roboto/system-ui as the only font with no pairing and no real type scale.
- A 3-column equal-width grid used for everything; every section carrying identical
  padding; a features grid of exactly 3 cards (icon + title + paragraph).
- Buttons and cards using bare defaults (`bg-blue-500`, `rounded-lg shadow-md`) with
  no hover state, no loading/error/empty state, no micro-interaction.
- No ARIA labels, color as the only meaning indicator, no visible focus state — the
  craft gaps and the accessibility gaps are usually the same gaps.

Call this out as a flag on the verdict. It is a pattern-match and carries no score
of its own.

## Step 4 — classify every finding

Three must-fixes is the right ceiling for what leads the output, but every other
finding still needs a home, and the class assigned tells the reader what to do with
it:

| Class | Meaning | What the reader does |
|---|---|---|
| **Must-fix** | Breaks the experience, blocks a task, or fails accessibility. Max 3. | Fix before shipping |
| **Should-fix** | Real cost to quality or conversion, but the design works without it | Fix this cycle |
| **Could-improve** | Craft and polish; defensible to leave as-is | Fix when touching that area |
| **Explore** | A real open question the critique can't settle | Route to research, don't argue |

**Explore is the class most critiques skip, and it's the honest one.** When a
disagreement rests on an assumption about users rather than a design principle,
saying so plainly is more honest than picking a side with confidence that wasn't
earned. Say what evidence would resolve it — a usability test, an A/B test, an
interview — rather than arguing it to a conclusion in the critique itself.

For each must-fix: what's wrong (specific location), why it matters (one line, tied
to a UX principle or cognitive-science basis), how to fix it
(specific and actionable), and the exact code fix if code was given.

## Step 5 — top 3 strengths to keep

For each: what's working, why it works (the principle that makes it effective), and
what would accidentally break it during iteration — the three things that would hurt
the design most if lost.

## Step 6 — one-line verdict

One direct, memorable sentence that captures this design's quality specifically —
never one that could apply to any design. Examples of the right shape: "A solid
foundation buried under visual noise — strip it back and you have something good."
"All the right components, none of the right hierarchy — this whispers when it
should shout." "Ship-ready craft with one fatal flaw: users can't find the primary
action."

## Output shape

```markdown
**Verdict:** [one line, specific to this design]

**Strengths (protect these)**
1. [Strength] — [why it works]

**Dimension scores**
| # | Dimension | Score | Observation |
|---|---|---|---|
...
**Total: X/100 — Grade: [letter]**

**Must-fix**
1. What / Why / Fix / Code (if applicable)

**Should-fix / Could-improve / Explore**
[grouped, one line each]

**Keep**
1. [Strength] — [what would break it]
```

## Quality bar

Every finding cites a UX principle or a specific location — "could be improved" with
nothing under it doesn't count. Most dimensions score 4–7; justify anything at an 8+
or a 3-. The verdict has to be specific to what was actually reviewed; a sentence that
would fit any design handed in does not count.
