---
name: gcp-review-audit-project
description: >-
  A user asks for a security look at a GCP project; the review skill should run, call gcloud only through its wrapper and finish with evidence, gaps and drafted fixes. Run with --allow-tools Bash so the Bash graders are meaningful; without it Bash is removed from the session.
tags: [gcp-review, should-trigger]
runs: 1
max_turns: 25
timeout_seconds: 600
allowed_tools: [Bash, Read, Glob, Grep, Skill]
---

We run our product on GCP in a project called acme-gov-dev and a customer security review is coming up. Can you go over the project's IAM, service account keys and org policies and tell me what looks too loose? gcloud is already set up on my machine.
