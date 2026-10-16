---
description: "Should trigger: two kinds of work that need different tiers"
tags: [trigger, model-choice]
max_turns: 12
timeout_seconds: 420
allowed_tools: [Read, Glob, Grep, Skill, WebFetch]
---
We have a nightly job that sorts about 5,000 support tickets into categories, and once a month we want a deep review of our service architecture before we commit to a big change. Which Claude model and effort should each one use?
