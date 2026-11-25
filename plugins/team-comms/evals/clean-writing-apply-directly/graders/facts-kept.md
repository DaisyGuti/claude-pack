---
type: regex
pattern: '^(?=[\s\S]*5000)(?=[\s\S]*dial tcp: i/o timeout)(?=[\s\S]*5432)(?=[\s\S]*https://example\.com/sqlpipe/network)'
match: contains
target:
  source: file
  path: README.md
---
