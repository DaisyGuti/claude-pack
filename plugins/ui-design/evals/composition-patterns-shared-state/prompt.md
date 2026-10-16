---
description: "Should-trigger: sibling components that need shared state."
tags: [trigger]
max_turns: 12
allowed_tools: [Skill, Read, Glob, Grep]
---

In our React app the message Composer owns its own state, but now the Send button, a character counter and a "Forward" dialog outside the Composer all need to read and change that state. We're passing props through four layers. What's the right structure?
