---
name: security-auditor-delegation
description: A request for a pre-release security audit should be delegated to the security-auditor agent.
tags: [agent, trigger]
max_turns: 12
allowed_tools: [Agent, Read, Glob, Grep]
---

We release next week. Have someone go through this repository for security problems and give me a
ranked list of what to fix first, with anything that is a false alarm weeded out.
