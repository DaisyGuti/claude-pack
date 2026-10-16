---
type: llm
---

PASS if the reply (1) flags the floating latest tag and recommends pinning the base image by digest,
(2) flags that the container runs as root and adds a non-root user, (3) flags DATABASE_PASSWORD as a
secret stored in the image and says it must not be in ENV (a BuildKit secret mount or a runtime
secret is the fix), (4) tells the user to rotate that password because it is already exposed, and
(5) shows a rewritten Dockerfile or the exact changes.

FAIL if the reply keeps the password in ENV or ARG, says the image is secure or compliant, or only
lists generic advice without a rewrite.
