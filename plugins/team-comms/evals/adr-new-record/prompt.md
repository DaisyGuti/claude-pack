---
max_turns: 25
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write, Edit]
---

We decided to use Postgres instead of DynamoDB for the audit log. Reports need joins and the team already runs Postgres. Write that up as an ADR. Decision makers are Priya and Marcus.
