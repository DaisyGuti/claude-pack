# Choosing a model and effort for the units you delegate

The eng agent reads this before it spawns anything. Sources: Claude Code sub-agents
documentation, sections "Choose a model" and "Choose an effort level"
(<https://code.claude.com/docs/en/sub-agents>), read 2026-10-16. Model names change, so
this file uses the aliases `haiku`, `sonnet` and `opus` and no version numbers.

## The rule

Size each unit by the hardest judgment it contains. A long job made of easy calls
stays on a cheap model. Start at the cheapest setting that should clear the bar, and
when one unit comes back weak, rerun that one unit a step up. Everything starting high
is the failure this file exists to prevent. A model the user or the caller names
outranks this table.

## Which model

| The unit's hardest call | `model` |
| --- | --- |
| Mechanical work with a crisp rubric: file inventories, scans, extraction, a rename, a config bump, wiring an existing check into an existing pipeline, collecting test output | `haiku` |
| Spec-driven implementation inside an existing seam, most bug fixes, research with citations, most verification and review | `sonnet` |
| Judgment where a wrong call is expensive to unwind: an architecture or contract choice, ambiguous multi-step work across a large context, what a guard does when it cannot resolve, whether a contradiction is real, review of authentication, authorization, payment, personal-data, migration or deletion changes | `opus` |

## How a spawn sets them

- The Agent tool takes `model` per spawn. Order of resolution: the spawn's `model`, then
  the agent file's `model`, then the `CLAUDE_CODE_SUBAGENT_MODEL` variable, then the
  parent's model.
- Effort comes from the agent file's `effort` field or the session. For a mechanical unit,
  pick an agent whose file already has a low effort.
- `isolation: "worktree"` on the spawn gives a write unit its own git worktree. By
  default it is branched from the default branch, so it lacks your current HEAD, and a unit that
  must see your uncommitted or unpushed work does not get a worktree; give it the path instead
  and make sure it is the only writer there.

## What each child gets

A child starts with no conversation history. Its brief states the goal, the exact files
it may touch, the interfaces or spec, the test command, how to commit (by path, on its
own branch, never push), and what to return. It also states any rule from the repo's
CLAUDE.md that bears on the unit, because a child does not know which of those matter.

**Return contract.** A child cuts narration and never cuts findings, error text,
`file:line` evidence or numbers. It quotes errors and exit codes as printed. When it finds
nothing, it says so in one line that names what it checked, so silence cannot pass for
success. When one unit fixes and another validates, keep them separate: only the
validator's result counts as validation.

## Escalating

Name which axis a weak result needs, in the report:

- **More depth on the same model.** You redid an analysis and only trusted a later pass,
  you held more call sites than you could track, or you know of an edge case you did not
  chase. The fix is a higher effort level.
- **A different kind of call.** The unit turned out to hold one of the `opus` judgments in
  the table. The fix is `model: opus` on the rerun.

An engineer cannot raise its own model or effort mid-run. It says which axis the work
needed and the caller reruns the unit.
