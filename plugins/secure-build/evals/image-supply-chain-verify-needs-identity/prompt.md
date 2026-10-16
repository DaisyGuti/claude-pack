---
name: image-supply-chain-verify-needs-identity
description: Verifying a signature must pin the signer identity and a digest; a request for a tag should be answered with that requirement.
tags: [image-supply-chain, should-trigger]
runs: 1
max_turns: 12
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill]
---

Check that us-docker.pkg.dev/acme-prod/apps/api:latest was really built by our GitHub pipeline and signed with cosign.
The repo is acme-corp/api and the workflow is .github/workflows/secure-build.yml on main.
