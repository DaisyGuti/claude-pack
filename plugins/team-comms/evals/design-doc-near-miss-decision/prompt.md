---
max_turns: 10
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill, Bash]
---

We picked Postgres over DynamoDB for the audit log because reports need joins. Record the decision.
