---
name: gitlab-migration-near-miss-gitlab-ci-job
description: >-
  A plain request for a GitLab CI job must be answered with the job and must not turn into a
  GitHub-to-GitLab migration plan. This is the near-miss case for the migration skill, which is
  user-invoked only (disable-model-invocation), so the check is on the content of the answer.
tags: [gitlab-migration, near-miss]
runs: 1
max_turns: 6
timeout_seconds: 240
allowed_tools: [Read, Glob, Grep]
expected_outcome: >-
  A .gitlab-ci.yml job that runs pytest on merge requests with a pip cache, and no migration plan.
---

Write me a .gitlab-ci.yml job that runs our Python unit tests with pytest on every merge request
and caches pip downloads between runs.
