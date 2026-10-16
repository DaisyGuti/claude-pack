---
name: security-scan-near-miss-dockerfile
description: Hardening a Dockerfile belongs to another plugin and should not load the security-scan skill.
tags: [near-miss]
max_turns: 8
allowed_tools: [Read, Glob, Grep, Skill]
---

Rewrite this Dockerfile so it runs as a non-root user and uses a minimal base image:

FROM python:3.12
COPY . /app
RUN pip install -r /app/requirements.txt
CMD ["python", "/app/main.py"]
