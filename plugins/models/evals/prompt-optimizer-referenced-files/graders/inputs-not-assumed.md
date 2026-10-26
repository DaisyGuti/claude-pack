---
type: llm
---
PASS if all three hold: (1) the prompt that handles the pull request first establishes what the pull request actually contains (code, documents or both) instead of assuming it is code; (2) no extraction depends on a single tool such as pdftotext, a Python library or LibreOffice without a fallback route or an instruction to stop and say what to install; (3) FIPS 199, which the user named but did not supply, gets its own extraction that downloads it from its publisher (NIST) and records the URL or version used.
FAIL if any of the three is missing, for example if FIPS 199 is left as an open question, is cited from memory, or the user is asked to supply a copy before any download is tried.
