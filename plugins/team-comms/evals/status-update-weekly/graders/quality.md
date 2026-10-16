---
type: llm
---

PASS if the update has Shipped, In progress, Next and Risks and asks style sections (empty
ones may be left out), is built from the git history (retry work, config fixes, docs), and
invents no tickets, numbers or dates.
FAIL if it invents work, or is a commit-by-commit list with no grouping.
