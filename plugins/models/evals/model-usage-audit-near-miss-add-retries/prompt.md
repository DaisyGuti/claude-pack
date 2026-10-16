---
description: "Near miss: a one-function code change is not an audit"
tags: [near-miss]
max_turns: 4
timeout_seconds: 120
allowed_tools: [Read, Glob, Grep, Skill]
---
Can you add retry logic with exponential backoff to this function?

def ask(client, question):
    return client.messages.create(model="claude-sonnet-5-5", max_tokens=500, messages=[{"role": "user", "content": question}])
