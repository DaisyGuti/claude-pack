# MADR guide

## Contents

- [What MADR is](#what-madr-is)
- [Sections](#sections)
- [Statuses and superseding](#statuses-and-superseding)
- [File names and numbering](#file-names-and-numbering)
- [A short example](#a-short-example)
- [Sources](#sources)

## What MADR is

MADR (Markdown Architectural Decision Records) is a lean markdown template for decision
records. The template this plugin uses follows MADR 4: front matter with `status`, `date`
and the people involved, then sections for the context, drivers, options, outcome and the
pros and cons of each option. Sections marked optional in MADR (drivers, consequences,
confirmation, pros and cons, more information) are in the template. Delete an optional
section that has nothing to say; `doc_tool.py adr check` requires only Context and Problem
Statement, Considered Options and Decision Outcome.

## Sections

| Section | What goes in it |
| --- | --- |
| Front matter | `status`, `date` of the last update, `decision-makers` (who decided), `consulted` (two-way), `informed` (one-way). Delete a line you cannot fill truthfully. |
| Title | The decision as a short phrase. |
| Context and Problem Statement | Two or three sentences or a short story. Phrase the question. Link the ticket or design doc. |
| Decision Drivers | The constraints and qualities that shape the choice. |
| Considered Options | A bullet per option, at least two. |
| Decision Outcome | `Chosen option: "<option>", because <reason>.` |
| Consequences | Good and bad results, each as "Good, because ..." or "Bad, because ...". |
| Confirmation | How the team checks the code follows the decision: a review step, a test, a lint rule, a fitness function. |
| Pros and Cons of the Options | A subsection per option with Good, Neutral and Bad lines. |
| More Information | Evidence, links to related records, and when to revisit the decision. |

Write the consequences honestly. A record with only good consequences gets ignored later.

## Statuses and superseding

Statuses: `proposed`, `accepted`, `rejected`, `deprecated`, and `superseded by [ADR-NNNN](file)`.

- A record moves forward by status. Its reasoning stays as written: later context goes in
  a new record that supersedes it.
- To replace a decision, create the new record with `--supersedes N`. The old record's
  status then points to the new one, and the new one links back.
- `deprecated` means the decision no longer applies and nothing replaces it.

## File names and numbering

Files are `NNNN-title-with-dashes.md`, numbered in creation order and never renumbered.
The width follows the folder's existing files and is four digits when the folder is new.
The folder is the one the repo already uses, else `docs/decisions`.

## A short example

```markdown
---
status: "accepted"
date: 2026-10-16
decision-makers: Priya, Marcus
---

# Use Postgres for the audit log

## Context and Problem Statement

Auditors ask for reports that join events to users and time ranges. Which store should
hold the audit log?

## Considered Options

- Postgres
- DynamoDB

## Decision Outcome

Chosen option: "Postgres", because the reports need joins and the team already runs it.

### Consequences

- Good, because reports are plain SQL.
- Bad, because the log table needs partitioning once it passes about a year of data.
```

## Sources

- MADR template and documentation: https://adr.github.io/madr/ and
  https://github.com/adr/madr (template read 2026-10-16).
