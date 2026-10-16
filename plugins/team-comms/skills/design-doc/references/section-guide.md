# Design doc section guide

## Contents

- [Shape and length](#shape-and-length)
- [Problem](#problem)
- [Goals and non-goals](#goals-and-non-goals)
- [Options](#options)
- [Recommendation](#recommendation)
- [Rollout](#rollout)
- [Open questions](#open-questions)
- [Common failures](#common-failures)

## Shape and length

A design doc is read by reviewers who have not seen the problem. It is short enough to read
in one sitting (two to five pages for most changes) and complete enough to decide from.
Use plain sentences. Put tables where data is tabular. Link instead of copying: tickets,
dashboards, earlier docs, the code involved.

Sections, in order: Problem, Goals, Non-goals, Options, Recommendation, Security and
compliance, Rollout, Open questions. `doc_tool.py design check` requires all of them.

## Problem

- Say what is wrong today in terms a reviewer can verify: an incident, a metric, a support
  volume, a deadline, a requirement from the program.
- Name who is affected and how often.
- Keep the solution out of this section. A problem that already contains its fix hides the
  other options.

## Goals and non-goals

- A goal is an outcome with a test: "p99 upload latency under 2 seconds at the current
  load", "a new engineer can run the service locally in 15 minutes".
- A non-goal is something a reasonable reader might expect and the work leaves out:
  "migrating existing records", "supporting the legacy client".
- Every option is judged against the goals. If an option needs a goal changed, say so.

## Options

- Include the option the user already prefers, the strongest alternative, and "Do nothing".
  Doing nothing has a cost and a duration; state them.
- For each option: how it works in a short paragraph; gains; costs and risks; effort
  (people and weeks, or a size such as S/M/L the team already uses).
- Add a comparison table when there are three or more options and two or more criteria:
  rows are options, columns are the criteria that decide the choice.
- Facts about outside systems (limits, prices, supported versions) come from the vendor's
  documentation, looked up now, with the link. Quote the numbers with the date read.

## Recommendation

- Name the option. Give the two or three facts that decide it.
- Say what would change the answer: "If load doubles before Q3, revisit option B."
- Record who agreed, when known, or leave that to the review.

## Rollout

- Phases with entry and exit criteria. A flag name where one exists.
- Who must be told, and when: on-call, support, the security reviewer, downstream teams.
- Rollback: the exact step, who can take it, how long it takes, and what data it leaves
  behind.
- Success signal: a metric or a check that shows the change worked, and how long to watch.
- Migration or backfill steps, with a way to stop and resume.

## Open questions

- A question a reviewer can answer, with an owner and a date.
- Questions that block the recommendation come first.
- Remove a question once it is answered, and record the answer in the section it affects.

## Common failures

- Options that are the same idea with different names.
- A recommendation with no stated reason.
- Rollout described as "deploy and monitor".
- A security section filled with general advice and no facts about this design.
- Numbers with no source.
