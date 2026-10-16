---
type: llm
---
PASS if the reply reports, with file and line evidence, at least these findings: a hard-coded API key (without printing its value), a model id that is deprecated or has a retirement date (claude-sonnet-4-5-20250929) taken from a provider page it fetched, no timeout or retry settings on the call, and a log line that writes the full prompt containing a patient note.
FAIL if it misses the hard-coded key or the logged prompt, prints the key, or states model lifecycle dates without having fetched a provider page.
