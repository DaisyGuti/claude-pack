# Choosing a base image

Contents:
- Decision order
- The options
- FIPS-capable choices
- Customer is DoD
- Digest pinning in practice
- Fetch these at run time
- Sources

## Decision order

1. Ask the customer's requirement first: FIPS 140 validated cryptography, a DoD-approved
   source (Iron Bank), or neither. This changes the shortlist more than any technical factor.
2. Prefer a distroless or minimal runtime image with no shell and no package manager.
3. Fall back to a slim image only when the runtime needs a shell or system package that a
   minimal image cannot give, and say why in a Dockerfile comment.
4. Build in a separate stage so compilers and package managers never reach the runtime image.

## The options

| Option | What it is | Cost | Notes |
|---|---|---|---|
| Google distroless (`gcr.io/distroless/*`) | Debian-based images with no shell or package manager; `static`, `base`, `cc`, language runtimes; `:nonroot` and `:debug` tags | Free | Signed with cosign keyless; verify with `cosign verify IMAGE --certificate-oidc-issuer https://accounts.google.com --certificate-identity keyless@distroless.iam.gserviceaccount.com`. Digest pinning and FIPS are not covered by its README. Use `:debug` only locally |
| Docker Hardened Images (DHI) | Hardened Alpine and Debian images, distroless variants, non-root, signed SBOMs, SLSA provenance | Community tier free under Apache-2.0; FIPS and STIG variants need a paid tier | Check the DHI catalog for the language and the tier |
| Chainguard Images | Minimal images rebuilt continuously | Free tier is a small set of images, `latest` tags only; pinned versions and FIPS variants need a paid tier | Pin by digest regardless |
| Red Hat UBI micro and minimal | `ubi-micro` has no package manager; `ubi-minimal` has `microdnf`; freely redistributable | Free to build on; Red Hat support needs a subscription | Fits FIPS hosts; see `templates/Dockerfile.ubi-fips` |
| Iron Bank | DoD hardened-image registry (`registry1.dso.mil`) | Registration with Platform One | Use when the customer is DoD; see below |
| Alpine, Debian slim, Ubuntu | General base images | Free | Builder stages, or runtime when a shell is required |

Availability, tiers and tags move. Open the vendor page before recommending one.

## FIPS-capable choices

FIPS 140 compliance belongs to a validated cryptographic module run in its approved mode,
inside a system an authorizing official accepts. An image never makes a system compliant.
Report which module the image uses, whether that module appears on the NIST CMVP validated
modules list, and whether the host enforces FIPS mode. Then stop; the decision belongs to a
person with the authority.

- **UBI on a FIPS host.** Containers inherit FIPS mode from the host kernel. On the host, `cat /proc/sys/crypto/fips_enabled` prints `1` when FIPS mode is on, and the same file read inside the container shows what the container sees. Confirm the host is FIPS-enabled before trusting the image.
- **Go.** The Go standard library ships a native cryptographic module. `GOFIPS140=v1.0.0 go build` selects the version, and `GODEBUG=fips140=on` turns FIPS mode on at run time. The Go documentation states which module versions carry a CMVP certificate and which are still in process: fetch https://go.dev/doc/security/fips140 and quote its status line for the version you use.
- **Docker Hardened Images and Chainguard.** Both offer FIPS variants on paid tiers. Fetch the vendor's current FIPS page and quote the validation claim.
- **Platform side.** On GCP, confirm what Google documents for the compute platform and for Assured Workloads before assuming the host layer. The `gcp-review` skill lists the Assured Workloads regimes to check.

## Customer is DoD

Iron Bank (`registry1.dso.mil`) is the DoD's hardened-image repository run by Platform One.
Access needs registration. When the customer requires Iron Bank images:

- Pull the base images from Iron Bank and set the registry in the `FROM` lines.
- Follow the Iron Bank hardening guide for repository structure, manifests and Dockerfile requirements if the team will submit its own image: https://docs-ironbank.dso.mil/
- Keep the digest pinning and non-root rules; they still apply.

Ask the user for the customer's current container policy document. Do not guess its terms.

## Digest pinning in practice

```sh
docker buildx imagetools inspect python:3.13-slim-trixie        # prints the index digest
```

Pin the index digest (the multi-architecture manifest list) so the same Dockerfile builds on
both amd64 and arm64. Let Renovate or Dependabot propose digest bumps as pull requests; the
`ci-harden` skill ships a Renovate config and a Dependabot config for that.

## Fetch these at run time

- The current tag and digest of every base image the Dockerfile will name.
- The vendor's FIPS and tier statement for any FIPS-capable image.
- The current CIS Docker Benchmark edition, when a report cites it.
- The CMVP validated modules list, when a report names a module's status.

## Sources

Fetched 2026-10-16.

- Distroless README: https://github.com/GoogleContainerTools/distroless
- Docker Hardened Images features: https://docs.docker.com/dhi/features/
- Docker Hardened Images announcement coverage: https://devclass.com/2025/12/18/docker-hardened-images-now-free-devs-give-cautious-welcome/
- Chainguard catalog starter: https://edu.chainguard.dev/chainguard/containers/about/catalog-starter/
- Chainguard FIPS documentation index: https://edu.chainguard.dev/chainguard/fips/fips-images/
- Iron Bank documentation: https://docs-ironbank.dso.mil/
- Red Hat, switching RHEL to FIPS mode (containers inherit host FIPS mode): https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/8/html/security_hardening/switching-rhel-to-fips-mode_security-hardening
- Go FIPS 140-3 guide: https://go.dev/doc/security/fips140
