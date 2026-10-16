---
name: eng
description: Slash entry for the engineering agent. Use when the user types /core:eng, or asks to "use eng", "run the engineering pass" or "have engineering do" a fix, feature, refactor or code review in the current repo, even if they do not name the agent. Hands the task to the core:eng agent in a fresh context and returns its report.
argument-hint: "[what to fix or build; add 'open a PR' or 'open an MR' to have the review opened]"
context: fork
agent: core:eng
background: false
---

Task: $ARGUMENTS

Work in the repository at the current working directory. Follow your own instructions end to
end and return your report. Open a pull request or merge request only if the task above says
to; otherwise leave the commit on its branch and return the drafted review for the user to
approve.

When the task above is empty, say that no task was given and stop.
