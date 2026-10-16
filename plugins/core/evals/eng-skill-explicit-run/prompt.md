---
description: "Should trigger: the user asks for the engineering pass by name."
max_turns: 8
allowed_tools: [Skill, Agent, Read, Glob, Grep]
---

Run the engineering pass on this: In utils.py the function paginate(items, page, size) returns
items[page * size:(page + 1) * size], but the UI sends 1-based page numbers, so page 1 skips
the first `size` items. Fix it and add a test.
