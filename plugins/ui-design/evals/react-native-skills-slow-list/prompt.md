---
description: "Should-trigger: a janky React Native list is the core list-performance problem."
tags: [trigger]
max_turns: 12
allowed_tools: [Skill, Read, Glob, Grep]
---

Our Expo app has a feed of about 2,000 posts rendered with a ScrollView and .map(), and scrolling stutters on mid-range Android phones. Each row builds its style object inline. What should I change?
