---
name: ci-harden-near-miss-code-review
description: A source-code security question is not a pipeline hardening request; the CI skill must not fire.
tags: [ci-harden, near-miss]
runs: 1
max_turns: 12
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill]
---

Is this Python function vulnerable to SQL injection? Show me the fixed version.

```
def get_user(conn, name):
    return conn.execute("SELECT * FROM users WHERE name = '%s'" % name).fetchone()
```
