---
type: llm
---
PASS if the reply contains a rewritten system prompt that (1) states the refund rule as a positive instruction with its reason or limit (14 days, human agent), (2) removes or tones down the emphatic wording ("NEVER", "ALWAYS", "CRITICAL", "!!!"), (3) says what to do when the knowledge base has no answer or the input is unclear, and (4) names a Claude model tier and an effort level for running it.
FAIL if the rewrite keeps the all-caps emphasis, drops the refund rule, or gives no model and effort.
