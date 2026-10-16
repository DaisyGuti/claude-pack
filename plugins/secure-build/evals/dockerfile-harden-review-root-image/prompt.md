---
name: dockerfile-harden-review-root-image
description: A Dockerfile with a floating tag, root user and a secret in ENV should trigger the Dockerfile hardening skill.
tags: [dockerfile-harden, should-trigger]
runs: 1
max_turns: 12
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill]
---

Can you review this Dockerfile for our API before it goes to production and fix what is wrong?

```
FROM python:latest
WORKDIR /app
COPY . .
ENV DATABASE_PASSWORD=s3cret-pass
RUN pip install -r requirements.txt
EXPOSE 8000
CMD python app.py
```
