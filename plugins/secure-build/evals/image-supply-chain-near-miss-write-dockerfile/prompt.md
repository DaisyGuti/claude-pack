---
name: image-supply-chain-near-miss-write-dockerfile
description: Writing a new Dockerfile is not image supply-chain work; the supply-chain skill must not fire.
tags: [image-supply-chain, near-miss]
runs: 1
max_turns: 12
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill]
---

Write me a Dockerfile for a small Flask app. The entry point is app.py and dependencies are in requirements.txt.
