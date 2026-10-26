---
type: llm
---
PASS if the final version runs from one session: the main prompt contains the extraction prompts (or is explicitly pasted together with them as one message) and an execution block or equivalent instruction that starts each extraction itself, for example one subagent per extraction, and waits for their notes files before the review begins.
FAIL if the user has to start the extraction prompts by hand, one at a time or in separate sessions, or if nothing in the main prompt starts them.
