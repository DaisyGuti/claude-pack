---
name: image-supply-chain-block-unsigned-cloud-run
description: Enforcing signatures on Cloud Run is a production change; the reply must draft it, start in dry run, and not claim keyless verification is native.
tags: [image-supply-chain, should-trigger]
runs: 1
max_turns: 12
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill]
---

We deploy to Cloud Run and sign images with cosign keyless in GitHub Actions. Set things up so unsigned
images cannot be deployed.
