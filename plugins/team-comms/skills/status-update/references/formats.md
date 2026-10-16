# Status update formats

## Contents

- [Standup](#standup)
- [Weekly update](#weekly-update)
- [Style rules](#style-rules)

## Standup

Use this for the daily post in a team channel or a standup thread.

```text
Yesterday
- Merged retry logic for uploads, https://example.com/acme/upload/pull/142
- Reviewed the SDK timeout change, https://example.com/acme/sdk/pull/88
Today
- Production cutover for the upload service (issue https://example.com/acme/upload/issues/21)
- Finish the load-test script on branch feature/load-test (2 commits, not pushed yet)
Blockers
- Waiting on platform for staging credentials, requested Monday
```

Rules:

- Three headings: Yesterday, Today, Blockers. Use "Friday" instead of "Yesterday" on a
  Monday, and name the day when the window covers a longer gap.
- One line per outcome, at most about eight lines in all.
- Each line ends with the link to the pull request, merge request or issue that backs it.
- Today lists open work from the data and anything the user adds. Mark a guess
  `[confirm: ...]`.
- Blockers says "None that I can see" when the data shows none, and the draft goes to the
  user for correction.

## Weekly update

Use this for a Friday summary to a team channel or a manager.

```text
Week of Oct 12: upload service migration on track for Oct 24.

Shipped
- Retry logic for uploads, merged Tuesday, https://example.com/acme/upload/pull/142
- Staging cutover, error rate flat at 0.2%, https://example.com/acme/upload/issues/19
In progress
- Production cutover plan, draft at https://example.com/acme/upload/pull/150
Next
- Production cutover Thursday Oct 22 at 10:00 ET
Risks and asks
- Rollback plan needs sign-off from Priya before Wednesday
```

Rules:

- The first line gives the state (on track, at risk, blocked, done) and the date it
  refers to. Take the state from the data and the user. If neither says, ask the user for it.
- Shipped lists merged requests and closed issues. In progress lists open and draft
  requests. Next lists dated plans that the user confirms. Risks and asks lists open
  questions and the people who must act, each with a date.
- Group related items into one line when several requests make one outcome.
- Leave out empty headings.

## Style rules

- Plain sentences. Past tense for Shipped and Yesterday, present or future for the rest.
- Numbers only when the data or the user supplied them.
- Use real names of pull requests and issues as titles, shortened when long.
- No hype words, no filler such as "making great progress", and no contrasting "not X"
  clause after a claim.
- Post in the team's thread when a standup thread exists. A weekly update is a new
  channel post.
