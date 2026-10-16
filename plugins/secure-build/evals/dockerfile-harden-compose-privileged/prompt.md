---
name: dockerfile-harden-compose-privileged
description: A Compose file with privileged mode, host networking and the Docker socket should trigger the hardening skill.
tags: [dockerfile-harden, should-trigger]
runs: 1
max_turns: 12
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill]
---

Our docker-compose file for the worker service is below. Is it safe to run this on a shared build host?

```
services:
  worker:
    image: registry.example.com/team/worker:latest
    privileged: true
    network_mode: host
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    environment:
      API_TOKEN: abc123def456
```
