---
description: "Should delegate a feature that touches authentication to the eng agent."
max_turns: 8
allowed_tools: [Skill, Agent, Read, Glob, Grep]
---

Add rate limiting to the /login endpoint of this service: five attempts per minute per IP, then a 429. Match how the rest of the service is built and include tests.
