---
type: llm
---

PASS if the reply uses or proposes a scanner (trivy or grype) and syft against the digest reference,
produces both CycloneDX and SPDX output, and reports findings or the exact commands. If a tool is not
installed it says so and names the install page. It states that the scan lists what was found and does
not claim the image is secure, compliant or ready.

FAIL if the reply says the image is safe or compliant, scans a tag instead of the digest it was given,
or invents vulnerability counts without running a scanner.
