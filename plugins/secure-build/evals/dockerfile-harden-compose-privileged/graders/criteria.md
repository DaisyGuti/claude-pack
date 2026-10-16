---
type: llm
---

PASS if the reply says this is not safe on a shared host and names each of: privileged mode,
host networking, the mounted Docker socket (container control of the host daemon), and the literal
token in the environment. It proposes a hardened service definition with a non-root user, a
read-only root filesystem, dropped capabilities and no-new-privileges.

FAIL if the reply approves the file as written or leaves privileged mode or the socket mount in
the proposed version.
