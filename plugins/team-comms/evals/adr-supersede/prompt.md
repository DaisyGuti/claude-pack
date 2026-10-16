---
max_turns: 25
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write, Edit]
---

Replace ADR 1: we now use Postgres for the audit log because reporting needs SQL joins. The old DynamoDB choice no longer holds.
