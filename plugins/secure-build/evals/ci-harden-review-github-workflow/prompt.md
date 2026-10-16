---
name: ci-harden-review-github-workflow
description: A workflow with unpinned actions, no permissions and a service-account key should trigger the CI hardening skill.
tags: [ci-harden, should-trigger]
runs: 1
max_turns: 12
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill]
---

Review this GitHub Actions workflow for security problems and tell me what to change:

```
name: deploy
on:
  pull_request_target:
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.event.pull_request.head.sha }}
      - uses: google-github-actions/auth@v2
        with:
          credentials_json: ${{ secrets.GCP_SA_KEY }}
      - run: echo "Deploying ${{ github.event.pull_request.title }}"
```
