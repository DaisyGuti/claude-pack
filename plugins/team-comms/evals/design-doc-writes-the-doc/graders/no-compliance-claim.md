---
type: regex
pattern: '\b(is|are|fully) compliant\b'
match: not_contains
flags: i
target:
  source: file
  path: docs/design/rate-limiting-for-the-public-api.md
---
