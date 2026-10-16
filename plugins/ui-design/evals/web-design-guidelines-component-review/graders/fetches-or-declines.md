---
type: llm
---

PASS if the reply either (a) reports findings in a terse file:line style that cover at least two real problems in the code (a clickable div, an icon-only button with no label, an image with no alt, an input with no label, outline removed, transition: all), or (b) says the current guidelines could not be fetched and declines to review from memory.
FAIL if it reviews the code while implying it read guidelines it did not fetch.
