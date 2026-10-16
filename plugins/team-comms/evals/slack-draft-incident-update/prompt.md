---
max_turns: 10
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill, Bash]
---

Draft an incident update for the #incidents thread. Facts: the Upload API started returning 500 for about 12 percent of requests at 14:05 UTC, right after the 13:58 UTC deploy of v2.4.1. Reads are fine. We are rolling back to v2.4.0, done by about 14:55 UTC. Next update at 15:00 UTC. I do not know the cause yet.
