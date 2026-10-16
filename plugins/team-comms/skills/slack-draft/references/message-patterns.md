# Message patterns for slack-draft

## Contents

- [Answer a question](#answer-a-question)
- [Ask for help](#ask-for-help)
- [Request a review](#request-a-review)
- [Status update](#status-update)
- [Incident update](#incident-update)
- [Announce a release](#announce-a-release)
- [Slack formatting](#slack-formatting)

Each pattern lists the order of the lines and an example. Examples use made-up names and
URLs. Replace every `<angle bracket>` with a real fact or ask for it.

## Answer a question

Order: the answer in one sentence, the reason, how to check it, a pointer for more.

```text
Yes, bump the timeout to 30s; the default 10s is shorter than the upload service's p99.

You can confirm it in the service dashboard: p99 for /upload was 14s over the last week.
The setting is `UPLOAD_TIMEOUT_SECONDS` in `deploy/values.yaml`.

Details are in https://example.com/docs/upload-timeouts
```

Rules: answer first. If the honest answer is "not sure", say so and say who would know. If
the answer has steps, number them. Quote only the command or config that matters.

## Ask for help

Order: the goal, what was tried, what is seen, the specific question, the deadline if any.
The reader should be able to answer without asking a follow-up.

```text
Question: how do I get a staging service account for the upload service load test?

Goal: run the load test against staging this week.
Tried: the request form (ticket <link>) 3 days ago, no reply yet.
Seen: `403 caller lacks storage.objects.create` from the test runner.

Does anyone own staging IAM, or is there a faster path? I need it by Thursday to keep the
release date.
```

Rules: first line is the question. Include exact error text in a code block. Name the
person or group asked only when one owns the answer. Do not write "quick question".

## Request a review

Order: what the change does in one sentence, size and risk, what to look at, the deadline,
the link. Post as a thread reply under the team's review thread when one exists.

```text
Review please: retry logic for the upload service (https://example.com/team/upload/-/merge_requests/142).

It retries failed writes 3 times with backoff. 3 files, about 120 lines, tests included.
Risk is low; the retry path is behind a flag, off by default.

Please look at the backoff math in `retry.py` and the flag wiring in `config.py`.
Needed by Thursday for the Friday release. @sam, you wrote the original client, so could
you take the first look?
```

Rules: one named reviewer at most per ask, with the reason. Say whether CI is green. Do not
paste the diff. Offer a short walkthrough only if the change is large.

## Status update

Order: state in one line, what changed since the last update, what is next, blockers and
asks. Use the `status-update` skill when the update comes from git and ticket history.

```text
Upload service migration: on track for Oct 24.

Since Monday: staging cutover done, error rate flat at 0.2%.
Next: production cutover Thursday 10:00 ET.
Need: sign-off on the rollback plan from @priya by Wednesday.
```

Rules: lead with the state in a word (on track, at risk, blocked, done) and the date it
refers to. Give a date for every "next". List asks last, each with an owner.

## Incident update

Order: status, impact, what is known, what is being done, next update time. Facts only.
Post in the incident thread so the history stays together.

```text
Update 14:40 UTC: Upload API errors continue; rollback in progress.

Impact: about 12% of upload requests return 500 since 14:05 UTC. Reads are fine.
Known: errors began right after the 13:58 deploy of v2.4.1.
Doing: rolling back to v2.4.0, expected complete by 14:55 UTC.
Cause: not yet confirmed.
Next update: 15:00 UTC, or sooner if status changes.
```

Rules: timestamps in UTC with the zone written. State impact in numbers when known and "not
yet measured" when not. Never name a cause as fact before it is confirmed; write
"suspected" and the evidence. Never name individuals as the cause. Set a time for the next
update and keep it. A resolution message states the end time, the fix, and where the
write-up will live.

## Announce a release

Order: what shipped and the version, what changes for the reader, anything they must do,
the link to the notes.

```text
Released upload-service v2.5.0.

What changes: uploads over 100 MB now resume after a dropped connection.
What you need to do: nothing for clients on the SDK 3.x; SDK 2.x clients must upgrade by
Nov 15 (the old resume endpoint is removed that day).
Notes: https://example.com/releases/upload-service-2.5.0
```

Rules: lead with the version. Say who is affected and who is not. List breaking changes
first and give the date. Use `@here` only for a breaking change that needs everyone.

## Slack formatting

- Slack's message tools accept standard markdown: `**bold**`, `_italic_`, `` `code` ``,
  fenced blocks, `> quote`, `- bullets`, `1.` numbered lists. Do not use Slack's older
  single-asterisk bold.
- Pasting into the Slack composer by hand may show the markers as plain text, depending on
  the user's "format messages with markdown" setting. Keep formatting light so a draft reads
  well either way: short lines, blank lines between thoughts, bullets, code fences.
- Tables work in sent messages but read poorly on mobile. Prefer bullets.
- One text block is limited to about 5,000 characters. Split a longer message into a
  thread, or move it to a canvas or a doc and link it.
- Dates: write the date and zone ("Thursday Oct 22, 10:00 ET").
