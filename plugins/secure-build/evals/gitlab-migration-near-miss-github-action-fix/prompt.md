---
name: gitlab-migration-near-miss-github-action-fix
description: >-
  A question about fixing a failing GitHub Actions step must be answered as a fix and must not
  produce a GitLab migration plan. Near-miss case for the migration skill, which is
  user-invoked only (disable-model-invocation), so the check is on the content of the answer.
tags: [gitlab-migration, near-miss]
runs: 1
max_turns: 6
timeout_seconds: 240
allowed_tools: [Read, Glob, Grep]
expected_outcome: >-
  An explanation of the npm peer dependency conflict and a fix for the workflow step, with no
  mention of moving to GitLab.
---

My GitHub Actions workflow fails at the "npm ci" step with "npm ERR! code ERESOLVE" and a message
about conflicting peer dependencies. The step is just `run: npm ci` after actions/setup-node@v4.
How do I fix it?
