---
name: gcp-review-near-miss-dockerfile
description: Reviewing a Dockerfile is not a review of GCP project configuration; the review skill must not fire.
tags: [gcp-review, near-miss]
runs: 1
max_turns: 10
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill]
---

Can you look over this Dockerfile and tell me what is risky about it?

```
FROM node:latest
WORKDIR /app
COPY . .
RUN npm install
ENV API_KEY=abc123
EXPOSE 3000
CMD ["npm", "start"]
```
