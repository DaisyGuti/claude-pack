---
type: llm
---

PASS if the reply drafts Binary Authorization setup as commands or policy for the user to run (it does not
claim to have applied anything), recommends starting in dry-run or audit-only mode before enforcement, and
explains that Binary Authorization verifies attestations or key-based signatures (for example a Cloud KMS
key) and does not itself verify keyless Sigstore identities, offering the choice between adding a KMS
signature and running a policy controller. It asks or states which option it assumes.

FAIL if it says keyless signatures work with Binary Authorization with no extra step, enables enforcement
immediately, or reports that it changed project settings.
