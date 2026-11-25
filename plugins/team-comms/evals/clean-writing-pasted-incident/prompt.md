---
description: "Pasted text: rewrite it plainly and keep every time and number."
max_turns: 8
allowed_tools: [Read, Glob, Grep, Skill, Bash]
---

This reads like AI wrote it. Clean it up before I send it to the team:

We have identified an issue that may have impacted some users' ability to upload files. Between 14:02 and 14:31 UTC, roughly 12% of requests to the Upload API failed — this was crucially tied to the 13:58 deploy of v2.4.1, which removed the cache warmup step. Our team has been working diligently to resolve this and services have now been fully restored. It is worth noting that reads were never affected. We sincerely apologize for any inconvenience this may have caused, and we will add a warmup check to the deploy pipeline this week.
