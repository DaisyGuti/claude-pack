---
type: llm
---

PASS if the reply identifies all of: actions referenced by tag instead of a full commit SHA, no permissions
block, pull_request_target combined with a checkout of the pull request's code, a long-lived service
account key (replace with OIDC and Workload Identity Federation), and the title expanded into run (script
injection, fix by passing it through env). It proposes corrected YAML or exact changes.

FAIL if it misses the pull_request_target checkout or the service account key, or says the workflow is secure.
