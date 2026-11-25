---
type: llm
---

PASS if the rewrite keeps every fact (14:02 to 14:31 UTC, about 12% of Upload API requests
failed, the 13:58 deploy of v2.4.1 removed the cache warmup step, reads were not affected,
a warmup check is coming this week), puts the impact in the first sentence, and uses short
active sentences in the simple past.
FAIL if it drops or changes any of those facts, adds a fact or cause that was not given,
keeps "We have identified", "diligently", "It is worth noting" or the apology filler, or
uses an em-dash.
