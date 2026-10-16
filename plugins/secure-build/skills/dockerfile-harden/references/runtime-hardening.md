# Runtime hardening

Contents:
- The five settings that matter most
- docker run and Compose
- Kubernetes and GKE
- Cloud Run
- Sources

A hardened image still runs with whatever rights the platform gives it. Set these where the
container is started.

## The five settings that matter most

1. Run as a non-root numeric user.
2. Make the root filesystem read-only and give writable paths a `tmpfs` or volume.
3. Drop all Linux capabilities and add back only a proven need.
4. Forbid privilege escalation (`no-new-privileges`).
5. Never run privileged, never share host namespaces, never mount the Docker socket.

## docker run and Compose

```sh
docker run --read-only --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  --cap-drop ALL --security-opt no-new-privileges:true \
  --user 65532:65532 --pids-limit 256 --memory 512m \
  -p 127.0.0.1:8080:8080 IMAGE@sha256:...
```

`templates/compose.hardened.yaml` carries the same settings for Compose. Run
`scripts/dockerfile_check.py` over a Compose file to see which are missing.

## Kubernetes and GKE

The Kubernetes Pod Security Standards "restricted" profile requires `runAsNonRoot: true`,
`allowPrivilegeEscalation: false`, `capabilities.drop: ["ALL"]` (only `NET_BIND_SERVICE` may
be added) and a `seccompProfile` of `RuntimeDefault` or `Localhost`. `readOnlyRootFilesystem`
is recommended and sits outside every profile.

```yaml
securityContext:            # container level
  runAsNonRoot: true
  runAsUser: 65532
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  capabilities:
    drop: ["ALL"]
  seccompProfile:
    type: RuntimeDefault
```

Enforce the profile with the namespace label `pod-security.kubernetes.io/enforce: restricted`.
The `gcp-review` skill covers GKE cluster-level settings (private nodes, Workload Identity,
Binary Authorization).

## Cloud Run

Cloud Run runs the container as root when the image sets no user, so a `USER` instruction
matters there. The container filesystem is writable and held in memory, which means writes
consume instance memory. Cloud Run does not support privileged containers or `setuid`
binaries. The service must listen on `0.0.0.0` on the port in the `PORT` variable. Dockerfile
`HEALTHCHECK` is ignored; configure startup and liveness probes on the service.

## Sources

Fetched 2026-10-16.

- Kubernetes Pod Security Standards: https://kubernetes.io/docs/concepts/security/pod-security-standards/
- Cloud Run container runtime contract: https://docs.cloud.google.com/run/docs/container-contract
