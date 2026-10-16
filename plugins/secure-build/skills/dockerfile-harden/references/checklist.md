# Dockerfile and image hardening checklist

Contents:
- How to use this list
- Build file rules (what `scripts/dockerfile_check.py` flags, with its rule id)
- Rules the script cannot see
- Mapping to hadolint and dockle
- Sources

## How to use this list

Each rule names the failure it prevents, the fix, and the check that finds it. The rule ids
`DH###` (Dockerfile) and `DC###` (Compose) belong to `scripts/dockerfile_check.py`. hadolint
ids (`DL####`) and dockle ids (`CIS-DI-####`, `DKL-DI-####`) are written exactly as those
tools print them.

The CIS Docker Benchmark section for container images and build file configuration is the
source of the `CIS-DI` family. Fetch the current benchmark edition from the Center for
Internet Security before citing a section number in a report; this file cites tool ids only,
because the tools' ids are checkable in their own repositories.

## Build file rules

| Id | Rule | Why | Fix | Also reported by |
|---|---|---|---|---|
| DH001 | Pin every base image by digest | A tag can be repointed; a digest cannot | `FROM image:tag@sha256:...`, bump with Renovate or Dependabot | dockle `DKL-DI-0006` (latest tag) |
| DH002 | Name a version tag, never `latest` | `latest` changes under you | explicit tag next to the digest | hadolint `DL3006`, `DL3007` |
| DH003 | Final stage runs as a non-root user | A container escape or file write starts with root's rights; Cloud Run runs as root when no user is set | `USER 65532:65532` (numeric, so Kubernetes `runAsNonRoot` can verify it) | hadolint `DL3002`, dockle `CIS-DI-0001` |
| DH004 | Split build and runtime stages | Compilers and caches in the runtime image are attack surface and weight | multi-stage with `COPY --from=build` | none |
| DH005 | `COPY` instead of `ADD`; `ADD` of a URL needs `--checksum` | `ADD` fetches and extracts implicitly | `COPY`; or `ADD --checksum=sha256:...` | hadolint `DL3020`, dockle `CIS-DI-0009` |
| DH006 | No secret in `ENV` or `ARG` | Both persist in image history and metadata | `RUN --mount=type=secret,id=NAME` with `docker build --secret id=NAME,src=FILE` | dockle `CIS-DI-0010` |
| DH007 | Never `COPY` key, `.env`, `.npmrc`, cloud credential files | A layer is permanent; deleting the file in a later layer leaves it in the earlier one | `.dockerignore` plus a secret mount | dockle `CIS-DI-0010` |
| DH008 | No `curl \| sh` | Runs unreviewed remote code with build rights | download, verify checksum or signature, then run | none |
| DH009 | apt/apk hygiene: `--no-install-recommends`, remove `/var/lib/apt/lists/*` in the same `RUN`, update and install in one `RUN`, `apk add --no-cache`, no `sudo`, no `dist-upgrade` | Smaller image, fewer packages, no stale index | one `RUN` per package step | hadolint `DL3015`, `DL3009`, `DL3019`, `DL3004`; dockle `CIS-DI-0007`, `DKL-DI-0005`, `DKL-DI-0004`, `DKL-DI-0001`, `DKL-DI-0003` |
| DH010 | `HEALTHCHECK` in the final stage | Lets Docker and Compose restart a wedged process | exec-form `HEALTHCHECK`; Kubernetes and Cloud Run ignore it, so also define a probe | dockle `CIS-DI-0006` |
| DH011 | No world-writable files, no setuid or setgid bits, no `EXPOSE 22` | Privilege escalation inside the container | narrowest `chmod`; remove sshd | dockle `CIS-DI-0008` |
| DH012 | Exec-form `CMD` and `ENTRYPOINT` | Shell form makes a shell PID 1, which does not forward signals | `CMD ["binary", "arg"]` | hadolint `DL3025` |
| DH013 | `.dockerignore` beside the Dockerfile | A broad `COPY .` otherwise sends `.git`, `.env` and keys into the context | start from `templates/dockerignore` | none |
| DH014 | No credentials inside a URL | Written into history and logs | credential helper or secret mount | none |

## Compose rules

| Id | Rule | Fix |
|---|---|---|
| DC001 | No `privileged: true` | remove; add one capability with `cap_add` if one is truly needed |
| DC002 | No `network_mode`, `pid`, `ipc` or `userns_mode` set to `host` | default isolated namespaces |
| DC003 | Never mount `docker.sock` | remove, or a socket proxy with a narrow allowlist |
| DC004 | Review every `cap_add`; `ALL`, `SYS_ADMIN`, `SYS_MODULE`, `SYS_PTRACE`, `SYS_RAWIO` are errors | add back only the proven need |
| DC005 | `cap_drop: [ALL]` | add it |
| DC006 | `read_only: true` with `tmpfs` for writable paths | add both |
| DC007 | `security_opt: [no-new-privileges:true]`; no `unconfined` profiles | add it, remove `unconfined` |
| DC008 | Pin `image:` by digest and name a tag | `image:tag@sha256:...` |
| DC009 | Set a non-root `user:` | numeric id |
| DC010 | Publish ports on `127.0.0.1` unless the network must reach them | `"127.0.0.1:8080:8080"` |
| DC011 | No literal secret in `environment:` | Compose `secrets:` or a value resolved outside the file |
| DC012 | `healthcheck:` | add it |
| DC013 | `pids_limit`, `mem_limit` or `deploy.resources.limits` | add them |

## Rules the script cannot see

The script reads text. These need a person or a tool that sees the built image:

- Whether a base image sets a non-root user in its own metadata (run `docker image inspect --format '{{.Config.User}}' IMAGE`).
- Which packages and CVEs the final image holds: scan it (see the `image-supply-chain` skill).
- Whether the image is minimal enough: run `dockle` and look at `docker history IMAGE`.
- Whether a `.dockerignore` rule is correct for the repository layout.
- Content trust and signing: Docker Content Trust is retired in favor of Sigstore signing; the `image-supply-chain` skill covers signing and verification.

## Mapping to hadolint and dockle

Run both when installed:

```sh
hadolint --format json Dockerfile          # Dockerfile text; GPL-3.0 licensed tool
dockle --format json --exit-code 1 --exit-level warn IMAGE   # built image; Apache-2.0
```

hadolint reads the Dockerfile and runs ShellCheck over `RUN` lines (ids `SC####`). dockle
reads a built image and prints `CIS-DI` (benchmark), `DKL-DI` (Docker) and `DKL-LI` (Linux)
checkpoints. Ignore a hadolint rule inline with `# hadolint ignore=DL3008` and say why in the
comment. Ignore a dockle checkpoint with `--ignore CIS-DI-0006` and say why in the report.

## Sources

Fetched 2026-10-16.

- Docker build best practices: https://docs.docker.com/build/building/best-practices/
- Docker build secrets: https://docs.docker.com/build/building/secrets/
- hadolint rules table: https://github.com/hadolint/hadolint
- dockle checkpoints: https://github.com/goodwithtech/dockle/blob/master/CHECKPOINT.md
- Docker Hardened Images on CIS Section 4 scope: https://docs.docker.com/dhi/explore/security-concepts/cis.md
