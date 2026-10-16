---
type: regex
pattern: '(peer[- ]dep|legacy-peer-deps|package-lock|npm install|--force|overrides)'
flags: i
match: contains
target: last_message
---
