---
name: threat-model-near-miss-scan
description: A request to scan code for leaked secrets should not load the threat-model skill.
tags: [near-miss]
max_turns: 8
allowed_tools: [Read, Glob, Grep, Skill]
---

Check this repository for hard-coded passwords and API keys before I push it.
