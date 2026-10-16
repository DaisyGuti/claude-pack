# Scanning an image and generating SBOMs

Contents:
- Resolve the digest first
- Scan with trivy (default) or grype
- Generate SBOMs with syft
- Reading the results
- Scanning in the registry
- Sources

## Resolve the digest first

Every command below takes `IMAGE@sha256:...`. A tag can move between the scan and the
deploy; a digest names one image.

```sh
docker buildx imagetools inspect IMAGE:TAG | awk '/^Digest:/ {print $2; exit}'
```

In CI the build step already outputs the digest (`docker/build-push-action` exposes
`steps.<id>.outputs.digest`); use that instead of looking it up.

## Scan with trivy (default) or grype

`scripts/image_evidence.sh` runs the whole pass and writes one directory of evidence:

```sh
sh ${CLAUDE_SKILL_DIR}/scripts/image_evidence.sh --fail-on HIGH IMAGE@sha256:... ./evidence
```

By hand, the same pass is:

```sh
trivy image --format json --output evidence/trivy.json --scanners vuln,secret IMAGE@sha256:...
```

Use grype when trivy cannot be installed on the machine (`--scanner grype` on the script):

```sh
grype IMAGE@sha256:... -o json > evidence/grype.json
grype sbom:./evidence/sbom.cdx.json      # scan an SBOM without pulling the image
```

Both tools download a vulnerability database on first use. On an air-gapped runner, mirror
the database and point the tool at the mirror (trivy documents DB mirror and offline flags at
https://trivy.dev/latest/docs/target/container_image/).

Trivy's `--ignore-unfixed` hides vulnerabilities that have no fix. Leave it off for evidence
reports: an unfixed critical vulnerability is still present. Turn it on in a CI gate only when
the team has agreed that policy, and write it down.

## Generate SBOMs with syft

Produce both common formats in one pass:

```sh
syft IMAGE@sha256:... -o cyclonedx-json=evidence/sbom.cdx.json -o spdx-json=evidence/sbom.spdx.json
```

Keep both: CycloneDX is what most vulnerability and license tools ingest, and SPDX is the
format federal customers most often name. Attach the SBOM to the image as a signed
attestation (see `sign-and-attest.md`) so it travels with the digest.

## Reading the results

- Group findings by package. One base-image bump usually clears a dozen CVE ids.
- A vulnerability in a package the runtime never loads is still reported. Say so, and do not
  suppress it without a recorded reason (VEX statements exist for this; propose one only when
  the user asks).
- Findings in a base image are fixed by moving to a newer base digest. Findings in
  application dependencies are fixed in the lockfile. Say which.
- Secrets found in a layer mean the secret is compromised. Rotate it; rebuilding without the
  file does not remove it from the registry's older layers.
- The summary lists what the scanner found. It never states that an image is safe, compliant
  or ready to deploy.

## Scanning in the registry

Artifact Registry can scan images on push with Artifact Analysis. The `gcp-review` skill
checks whether the scanning API is enabled for a project and whether repositories have it
on. Registry scanning and a CI scan complement each other: CI blocks a bad build, and the
registry keeps re-scanning images already stored as new CVEs are published.

## Sources

Fetched 2026-10-16.

- Trivy image scanning: https://trivy.dev/latest/docs/target/container_image/
- Syft: https://github.com/anchore/syft (Apache-2.0)
- Grype: https://github.com/anchore/grype (Apache-2.0)
