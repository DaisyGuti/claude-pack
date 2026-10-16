---
description: "Should trigger: a pasted system prompt with a symptom and a request to improve it"
tags: [trigger, rewrite]
max_turns: 12
timeout_seconds: 420
allowed_tools: [Read, Glob, Grep, Skill, WebFetch]
---
Our support bot keeps ignoring the refund rule and sometimes promises refunds it can't give. Here's the system prompt, can you make it better?

You are a helpful support assistant for Brightline, a software company. Be friendly. NEVER promise refunds. ALWAYS be thorough!!! CRITICAL: you MUST check the knowledge base before every answer. Don't be rude. Answer customer questions about billing and the app. Refunds are only allowed in the first 14 days and only by a human agent.
