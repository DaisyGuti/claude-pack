---
name: security-auditor-near-miss-bugfix
description: An ordinary bug fix should not be sent to the security auditor.
tags: [agent, near-miss]
max_turns: 8
allowed_tools: [Agent, Read, Glob, Grep]
---

This function should return the sum of the list but it returns None for an empty list. Fix it:

def total(items):
    if items:
        return sum(items)
