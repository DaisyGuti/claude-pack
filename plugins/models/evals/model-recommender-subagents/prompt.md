---
description: "Should trigger: choosing models for Claude Code subagents"
tags: [trigger, claude-code]
max_turns: 12
timeout_seconds: 420
allowed_tools: [Read, Glob, Grep, Skill, WebFetch]
---
Our Claude Code helper agents that only grep the repo and list files are running on Opus and burning through usage. What should I change so they use something cheaper, and how do I make sure it's still good enough?
