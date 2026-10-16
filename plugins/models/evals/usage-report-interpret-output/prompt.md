---
description: "Should trigger: interpreting a pasted usage report; the judgment run stays on the top tier"
tags: [trigger, interpretation]
max_turns: 6
timeout_seconds: 240
allowed_tools: [Read, Skill, WebFetch]
---
Here's the output of my usage report. What should I change?

By model
  model                 tier     calls   cost
  claude-opus-5-5       top        412   $61.20
  claude-sonnet-5-5     mid       1890   $38.75

Top-tier subagent runs that look mechanical (leads to confirm, not verdicts)
  explorer: 'list every file that imports the billing module' on claude-opus-5-5 (asked for inherit), 9 calls, 1450 out, $2.10
      tools: {'Grep': 7, 'Read': 4}; same tokens would cost about $0.74 at mid, $0.06 at small
  security-reviewer: 'review the new token refresh flow for flaws' on claude-opus-5-5 (asked for opus), 14 calls, 3900 out, $4.80
      tools: {'Read': 11, 'Grep': 6}; same tokens would cost about $1.70 at mid, $0.12 at small
