---
type: llm
---

PASS if the reply says the check must run against a digest rather than the latest tag (and shows how to
resolve the digest), and gives a cosign verify command that pins both the signer identity
(https://github.com/acme-corp/api/.github/workflows/secure-build.yml@refs/heads/main) and the issuer
https://token.actions.githubusercontent.com. It does not use a wildcard or regexp identity that would
accept other repositories.

FAIL if it verifies without identity flags, accepts any signer, or reports the image as verified without
having run a verification.
