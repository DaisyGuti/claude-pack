---
name: gcp-review-near-miss-terraform
description: Writing new Terraform for a GCS bucket is not a review of existing configuration; the review skill must not fire.
tags: [gcp-review, near-miss]
runs: 1
max_turns: 10
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Write, Skill]
---

Write me a Terraform file for a new Google Cloud Storage bucket for our build artifacts. It should be in us-central1, use uniform bucket-level access, and delete objects after 30 days.
