---
description: "Should delegate a bug fix to the eng agent."
max_turns: 8
allowed_tools: [Skill, Agent, Read, Glob, Grep]
---

In utils.py the function paginate(items, page, size) returns
items[page * size:(page + 1) * size], but the UI sends 1-based page numbers, so page 1 skips
the first `size` items. Fix it and add a test.
