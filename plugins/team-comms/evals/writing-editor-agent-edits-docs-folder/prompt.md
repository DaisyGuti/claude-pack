---
description: "Delegation: an editing pass over a docs folder goes to the writing-editor agent."
tags: [agent, trigger]
max_turns: 12
timeout_seconds: 600
allowed_tools: [Agent, Read, Glob, Grep, Skill]
---

Every file in docs/ is wordy and full of filler. Run an editing pass over each one, in parallel if you can, and show me the proposed rewrites before anything changes.
