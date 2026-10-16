---
name: image-supply-chain-scan-and-sbom
description: Scanning a pushed image and producing SBOMs should trigger the supply-chain skill.
tags: [image-supply-chain, should-trigger]
runs: 1
max_turns: 12
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill, Bash]
---

We just pushed us-docker.pkg.dev/acme-prod/apps/api@sha256:3a4ca3561be49adc1f75317c02711e96ac181b8f35734cad5ffa4251e139ee58 .
Scan it for vulnerabilities and give me SBOMs in CycloneDX and SPDX for the customer.
