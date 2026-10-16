# Signing, attestations and provenance

Contents:
- Choose how to sign
- Keyless signing with cosign in CI
- Signer identities to verify against
- Attest the SBOM and provenance
- SLSA provenance on GitHub
- SLSA provenance on GitLab
- Verify before deploy
- Sources

## Choose how to sign

| Option | Needs | Strengths | Watch for |
|---|---|---|---|
| Keyless cosign (default) | The CI job's OIDC token; Sigstore's Fulcio and Rekor | No key to store or rotate; the signature proves which workflow built the image | The signing certificate holds the workflow identity, which includes the repository path. Entries in the public Rekor log are public and permanent. Decide whether that is acceptable for a private government repository |
| cosign with a Cloud KMS key | A KMS key and CI permission to use it, reached through Workload Identity Federation | Key never leaves KMS; Binary Authorization's Sigstore check and attestors can verify it | Key IAM and rotation to manage |
| GitHub artifact attestations | GitHub only | Built into Actions | Private repositories need GitHub Enterprise Cloud; private repos use GitHub's own Sigstore instance, which federates only with GitHub Actions |

Keyless signatures through the CI identity are the default in this plugin's pipelines. If the
customer needs Google's Binary Authorization to enforce signatures, add the KMS signature too
(`binary-authorization.md`). Present the Rekor visibility trade-off to the user as a decision
and let them pick.

## Keyless signing with cosign in CI

Sign the digest, never a tag. The job needs the OIDC token: `id-token: write` on GitHub, an
`id_tokens:` entry with `aud: sigstore` on GitLab (the reference pipelines in the `ci-harden`
skill already do both).

```sh
cosign sign --yes "$IMAGE@$DIGEST"
```

`--yes` skips the interactive confirmation that a CI job cannot answer.

## Signer identities to verify against

Verification pins two facts: the identity of the signing workflow and the OIDC issuer that
vouched for it. Write both in full; never use a wildcard that covers other repositories.

| Host | Issuer | Identity |
|---|---|---|
| GitHub Actions | `https://token.actions.githubusercontent.com` | `https://github.com/ORG/REPO/.github/workflows/FILE.yml@refs/heads/main` |
| GitLab CI | `https://gitlab.com` (self-managed: the instance URL) | `https://gitlab.com/GROUP/PROJECT//.gitlab-ci.yml@refs/heads/main` |

GitLab puts a double slash before the CI file path; a single slash fails verification.

## Attest the SBOM and provenance

An attestation binds a statement (an SBOM, a scan result, provenance) to the image digest and
signs it.

```sh
cosign attest --yes --type cyclonedx --predicate evidence/sbom.cdx.json "$IMAGE@$DIGEST"
cosign attest --yes --type spdxjson   --predicate evidence/sbom.spdx.json "$IMAGE@$DIGEST"
```

## SLSA provenance on GitHub

Two routes exist; verify the one you use against its current documentation.

- `actions/attest` creates provenance and SBOM attestations for a subject digest. GitHub's
  documentation states that artifact attestations alone provide SLSA v1.0 Build Level 2 and
  that reusable workflows, which isolate the build from the calling workflow, are the route
  to Build Level 3. It is available in private repositories only on GitHub Enterprise Cloud.
- `slsa-framework/slsa-github-generator` ships a reusable workflow for container images
  (`generator_container_slsa3.yml`). For private repositories it requires opting in with
  `private-repository: true`, and its documentation warns that every build then posts an
  entry to the public Rekor instance, which leaks the repository name.

## SLSA provenance on GitLab

GitLab Runner can generate an in-toto statement with a SLSA 1.0 provenance predicate for a
job's artifacts when `RUNNER_GENERATE_ARTIFACTS_METADATA` is `"true"`. The file is named
`{ARTIFACT_NAME}-metadata.json` (or `artifacts-metadata.json`). GitLab's documentation does
not state a SLSA level for it and the runner does not sign it. To bind provenance to an image,
generate the statement and attach it with `cosign attest --type slsaprovenance`.

Do not write a SLSA level into a report unless the platform's own documentation states it for
the setup in use. Quote that statement and its source.

## Verify before deploy

```sh
sh ${CLAUDE_SKILL_DIR}/scripts/verify_image.sh --host github \
  --identity "https://github.com/ORG/REPO/.github/workflows/secure-build.yml@refs/heads/main" \
  --attestation cyclonedx IMAGE@sha256:...
```

The script refuses tags, refuses wildcard identities, and pins the issuer. It wraps
`cosign verify` and `cosign verify-attestation`.

## Sources

Fetched 2026-10-16.

- Sigstore cosign signing overview: https://docs.sigstore.dev/cosign/signing/overview/
- Sigstore security model, Rekor: https://docs.sigstore.dev/about/security/
- GitLab keyless signing examples: https://docs.gitlab.com/ci/yaml/signing_examples/
- GitLab runner artifact provenance: https://docs.gitlab.com/ci/runners/configure_runners/
- GitHub artifact attestations concepts: https://docs.github.com/en/actions/concepts/security/artifact-attestations
- actions/attest: https://github.com/actions/attest
- SLSA GitHub generator, container: https://github.com/slsa-framework/slsa-github-generator/blob/main/internal/builders/container/README.md
