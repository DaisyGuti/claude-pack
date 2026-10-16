---
name: dockerfile-harden-near-miss-scan-image
description: Scanning a built image for CVEs and making an SBOM is supply-chain work; the Dockerfile skill must not fire.
tags: [dockerfile-harden, near-miss]
runs: 1
max_turns: 12
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill]
---

We just pushed us-docker.pkg.dev/acme-prod/apps/api@sha256:3a4ca3561be49adc1f75317c02711e96ac181b8f35734cad5ffa4251e139ee58 .
Which tools would you use to list its vulnerabilities and produce an SBOM for the customer?
