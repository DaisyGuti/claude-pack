---
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Bash, Write, Edit]
---

Write a design doc titled "Rate limiting for the public API". Our public gateway has no rate limits and a scraper took down form intake last month. The forms take personal information. R&D project on GCP. Options on the table: a token bucket at the gateway, per-service middleware, or a managed WAF rule.
