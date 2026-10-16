---
name: security-scan-trigger
description: A request to run the installed scanners and merge the results should load the security-scan skill.
tags: [trigger]
max_turns: 12
allowed_tools: [Read, Glob, Grep, Skill]
---

I am about to merge this branch. Run whatever security scanners we have installed against the repo
and give me one list of the problems they find, with the file and line for each.
