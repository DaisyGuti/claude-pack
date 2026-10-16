---
name: dockerfile-harden
description: >-
  Reviews and rewrites Dockerfiles and Docker Compose files for container hardening:
  multi-stage builds, minimal or distroless base images (with FIPS-capable and DoD Iron Bank
  options for government work), base images pinned by digest, non-root USER, no secrets in
  layers (BuildKit secret mounts), .dockerignore, healthchecks, and runtime settings such as
  read-only root filesystem, dropped capabilities and no-new-privileges. Runs hadolint and
  dockle when installed and ships reference Dockerfiles. Use it for "review my Dockerfile",
  "harden this container", "make this image smaller or safer", "why does the image run as
  root", "fix secrets in my Docker build", "write a production Dockerfile", or a Compose file
  with privileged, host networking or the Docker socket, even when the user does not say
  "hardening". For scanning, SBOMs and signing a built image use image-supply-chain; for
  pipelines use ci-harden.
allowed-tools: Read Grep Glob Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/*)
---

# Hardening Dockerfiles and Compose files

Review the files, fix what the evidence shows, and prove the result still builds and runs.
Do the work; do not hand back a list of suggestions.

## Steps

1. **Find the files.** Glob for `Dockerfile*`, `*.Dockerfile`, `compose*.y*ml`,
   `docker-compose*.y*ml` and `.dockerignore`. Read each one before judging it.
2. **Run the checker.** Execute (do not read) the bundled script and read its output:

   ```sh
   python3 ${CLAUDE_SKILL_DIR}/scripts/dockerfile_check.py <file-or-directory> ...
   ```

   Findings carry a rule id, a line and a fix. `references/checklist.md` explains each id and
   maps it to hadolint and dockle ids. The script is text-level and uses the standard library
   only. A clean result covers what the text shows and nothing more.
3. **Run the fuller linters when present.** Check with `command -v hadolint dockle`. Run
   `hadolint --format json <Dockerfile>` on every Dockerfile. Run
   `dockle --format json <image>` only on an image that already exists locally. When a tool is
   missing, say so in the report and carry on; link the project page
   (https://github.com/hadolint/hadolint, https://github.com/goodwithtech/dockle) instead of
   installing anything.
4. **Settle the base image.** Ask one question only if it matters and the repository does not
   answer it: does the customer require FIPS 140 cryptography or DoD Iron Bank images? If the
   answer is unknown, assume neither and say so. Choose from `references/base-images.md`.
5. **Rewrite from the nearest template** in `${CLAUDE_SKILL_DIR}/templates/`
   (`Dockerfile.python`, `.node`, `.go`, `.ubi-fips`, `compose.hardened.yaml`, `dockerignore`).
   Keep the application's behavior: same ports, entrypoint semantics and file layout unless a
   finding requires a change. Resolve every digest at run time:

   ```sh
   docker buildx imagetools inspect <image:tag>
   ```

   When the registry is unreachable, leave a clearly named placeholder and report it. Never
   write a digest from memory.
6. **Verify.** Re-run the checker. When Docker is available and the user agrees to a build,
   build the image and run it with the hardened flags from
   `references/runtime-hardening.md`; confirm it starts and passes its health probe. When a
   build is not possible, say what was not run.
7. **Report** under these headings: *Fixed* (rule id, file, one line), *Still open* (with the
   reason and who decides), *Not checked* (tools missing, build not run, behavior only a
   running system shows).

## Rules that decide most reviews

- Pin every `FROM` by digest next to a version tag. Never `latest`.
- Final stage runs as a numeric non-root user. Cloud Run runs as root without one.
- Secrets never enter `ENV`, `ARG`, `COPY` or a `RUN` argument. Use a BuildKit secret mount:

  ```dockerfile
  RUN --mount=type=secret,id=npmrc,target=/root/.npmrc npm ci
  ```

  ```sh
  docker build --secret id=npmrc,src=.npmrc .
  ```

  A secret that already reached a layer or the git history is compromised: tell the user to
  rotate it, because deleting the line does not remove it.
- Build tools stay in a build stage. The runtime stage copies only the artifact.
- `HEALTHCHECK` and `CMD` use exec form. Distroless images have no shell or curl, so the
  probe is the runtime binary.
- Provide a `.dockerignore`. Start from `templates/dockerignore`.

## Side effects of hardening to warn about

- A read-only root filesystem breaks any process that writes outside a mounted `tmpfs` or
  volume. List the paths the app writes before turning it on.
- A distroless runtime breaks entrypoint shell scripts, `docker exec ... sh` debugging and
  shell-form commands. Use the `:debug` variant locally only.
- Dropping all capabilities breaks binding ports below 1024 as non-root; use a port above
  1024 or add `NET_BIND_SERVICE` deliberately.
- Changing the base image changes the C library, timezone data and certificate store. Run the
  application's own tests against the new image.

## Boundaries

- Scanning a built image, SBOMs, signing and Artifact Registry: `image-supply-chain`.
- Pipelines that build the image: `ci-harden`.
- Source-code scans and threat models: the `security` plugin.
- GKE, Cloud Run and project-level settings: `gcp-review`.
- Standards language: this skill produces evidence and fixes. It never states that an image
  is compliant, FIPS-validated or authorized; a person with the authority decides.

## References

- `references/checklist.md`: every rule, why it matters, the tool ids that report it.
- `references/base-images.md`: base image options, FIPS-capable choices, DoD Iron Bank, what to fetch at run time.
- `references/runtime-hardening.md`: docker run, Compose, Kubernetes and Cloud Run settings.

Tools used: `python3` 3.11+ (bundled script); optional `hadolint`, `dockle`, `docker` with
BuildKit. Check each with `command -v <tool>`.
