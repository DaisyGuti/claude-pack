# Plain English

Rules that make text readable on one pass by a smart reader outside the field, adapted from
[SimpleEnglish](https://github.com/AminBlg/SimpleEnglish) (MIT), which draws on the
ASD-STE100 Simplified Technical English standard. Read it for the plain-English pass.

## Sentences and words

- Sort each passage. Procedural text tells the reader what to do: imperative mood, one
  instruction per sentence, at most 20 words. Descriptive text explains: simple tenses, at
  most 25 words, one topic per paragraph, at most six sentences per paragraph.
- Count code, a path, a number with its unit or a quoted label as one word.
- Give the reader each term and each fact before the step that needs it. Name the host, the
  flag or the earlier step a command depends on: "Restart the `sync` service on the host
  that runs the job."
- Noun chains of three words at most. Break longer ones with a preposition: "the timeout
  value for the connection pool".
- Describe an action with a verb: "compress the file" beats "perform compression of the
  file".
- Fix an agentless passive with "you" (the reader) or "we" (the team): "Indexes are not used
  on this table" becomes "We do not use indexes on this table."
- A vertical list needs three or more parallel items or steps: a colon on the lead-in, one
  instruction per item, no nesting.
- A note gives information. A limit or instruction belongs in the step it governs, so the
  procedure still works for a reader who skips every note.
- American spelling.

## The modal ladder

| Written | Write instead |
| --- | --- |
| `should` (a requirement) | must |
| `should` (a recommendation) | delete it, or state the fact: "X is faster because Y." |
| `should a failure occur` | if: "If a failure occurs" |
| `may`, `might`, `could` (a possibility) | can |
| `may` (permission) | can |
| `would` (a hypothetical) | can, or "If X occurs, Y occurs." |

## Patterns by kind of text

| Text | Pattern |
| --- | --- |
| Error message | What happened (simple past), the cause if known, the fix as a command. "Connection to the database failed. The password for user `app` was wrong. Set `DB_PASSWORD` and connect again." |
| Runbook | Imperative steps, one instruction each, condition first, the warning before its step. |
| Incident report | Simple past with times. Say "unknown" for what is unknown. "Between 14:02 and 14:31 UTC, 12% of requests failed." |
| Release note | One change per entry. A breaking change leads with the action: "Update your calls to `/v2/users`. The `name` field split into `first_name` and `last_name`." |
| Commit, PR or MR body | Imperative subject line. The body says what changed and why. Delete "This PR aims to". |
| Ticket | The problem or ask in the first line, then facts and acceptance points. |
| Message | The point or the ask in the first line, then the facts the reader needs to act. |
| Agent prompt or skill | One instruction per sentence, condition first, `must` for a rule. A model reads `should` as optional. |
| UI copy | Buttons and labels are names and stay. Body copy follows the rules: "No projects yet. Create a project to start." |
