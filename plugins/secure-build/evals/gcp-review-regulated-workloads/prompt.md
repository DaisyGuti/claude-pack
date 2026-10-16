---
name: gcp-review-regulated-workloads
description: >-
  A user asks what can be checked for FedRAMP High and IL5 workloads on GCP; the skill should answer with evidence and gaps and never claim compliance. Run with --allow-tools Bash so the Bash graders are meaningful; without it Bash is removed from the session.
tags: [gcp-review, should-trigger, compliance]
runs: 1
max_turns: 20
timeout_seconds: 600
allowed_tools: [Bash, Read, Glob, Grep, Skill, WebFetch]
---

We're moving a government pilot onto GCP and the program office keeps saying we need FedRAMP High, maybe IL5, using Assured Workloads. Before I go to them, what can you check in our GCP organization with gcloud, and what would you not be able to tell me?
