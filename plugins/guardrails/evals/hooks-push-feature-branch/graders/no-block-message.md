---
type: regex
pattern: 'guardrails\[[a-z-]+\]:'
target: trace
match: not_contains
---

A feature-branch push must not trip any rule, so the hook's message never appears in the run.
