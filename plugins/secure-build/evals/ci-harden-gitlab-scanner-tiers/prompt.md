---
name: ci-harden-gitlab-scanner-tiers
description: Asking which GitLab scanners run on the Free tier should trigger the CI hardening skill and be answered from current documentation.
tags: [ci-harden, should-trigger]
runs: 1
max_turns: 12
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill, WebFetch, WebSearch]
---

We are moving to GitLab on the Free plan. Which of GitLab's built-in security scanners will actually work for us,
which need Ultimate, and what do we use instead for the ones we cannot have?
