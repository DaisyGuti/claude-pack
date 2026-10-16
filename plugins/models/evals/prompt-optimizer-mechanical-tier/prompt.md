---
description: "Should trigger and choose the smallest tier for a mechanical, high-volume prompt"
tags: [trigger, model-choice]
max_turns: 12
timeout_seconds: 420
allowed_tools: [Read, Glob, Grep, Skill, WebFetch]
---
Can you tighten this prompt and tell me what to run it on? It runs about 20,000 times a day.

Read the support ticket below and return JSON with two fields: "category" (one of billing, bug, feature_request, other) and "urgent" (true or false). Return only the JSON.

<ticket>{{ticket_text}}</ticket>
