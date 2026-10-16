---
type: llm
---

PASS if the reply sorts the log into decisions, asks of the user, blockers and FYIs; lists the
skipped canary as a decision, Marcus's approval request as an ask of the user, and Lena's
pending credentials as a blocker; and leaves out the lunch order.
FAIL if the reply is a message-by-message retelling, invents a link or a name not in the log,
or includes the lunch order.
