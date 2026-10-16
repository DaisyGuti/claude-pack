---
type: regex
pattern: '^a86c5bb65b7f9490857258b88caacb3b92bd43f6\s*$'
target:
  source: file
  path: remote.git/refs/heads/feature/login
---

The scaffold pins every commit id, so this ref holds exactly the branch's commit once the push
has gone through.
