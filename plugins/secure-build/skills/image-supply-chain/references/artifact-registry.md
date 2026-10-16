# Pushing to Google Artifact Registry

Contents:
- One-time setup (a human runs these)
- Authenticate CI without a key file
- Push and record the digest
- Immutable tags and signatures
- Sources

Everything under "One-time setup" changes cloud state. Draft the commands, show them, and let
the user run them; do not run them from this skill.

## One-time setup (a human runs these)

```sh
gcloud artifacts repositories create REPOSITORY \
  --repository-format=docker --location=LOCATION \
  --description="Application images" \
  --immutable-tags
# Add --kms-key=projects/P/locations/L/keyRings/R/cryptoKeys/K for customer-managed encryption.

gcloud artifacts repositories add-iam-policy-binding REPOSITORY --location=LOCATION \
  --member="serviceAccount:ci-publisher@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.writer"
```

The image path is `LOCATION-docker.pkg.dev/PROJECT/REPOSITORY/IMAGE`. Grant
`roles/artifactregistry.writer` to the CI publisher service account on this one repository (never on
the project), and `roles/artifactregistry.reader` to the runtime identities that pull.

The pool, provider, attribute conditions and the service account that CI impersonates are in
`ci-harden/references/gcp-workload-identity.md`.

## Authenticate CI without a key file

GitHub Actions: `google-github-actions/auth` with `workload_identity_provider` and, for
Docker, `token_format: access_token`, then log in to the registry with username
`oauth2accesstoken`. GitLab CI: exchange the `id_tokens:` JWT through Workload Identity
Federation. Both are in the reference pipelines under `ci-harden/templates/`. A downloaded
service-account key is never the answer; `gcp-review` flags user-managed keys.

Access tokens last 60 minutes; request one shortly before use.

## Push and record the digest

Push by building with `docker/build-push-action` (GitHub) or `docker buildx build --push`
(GitLab), take the digest from the build output, and use `IMAGE@sha256:...` for every later
step: scan, SBOM, sign, attest, deploy.

## Immutable tags and signatures

`--immutable-tags` makes a tag point to one digest forever, which is what a release pipeline
wants. cosign stores signatures and attestations in the same repository under tags derived
from the image digest, so it may need to write the same tag more than once. UNVERIFIED: this
build had no GCP project, so the interaction of immutable tags with cosign signature tags was
not tested. Test it in a scratch repository before enabling immutability on the production
repository, and record the result.

## Sources

Fetched 2026-10-16.

- Artifact Registry Docker authentication: https://docs.cloud.google.com/artifact-registry/docs/docker/authentication
- Create standard repositories (immutable tags, CMEK): https://docs.cloud.google.com/artifact-registry/docs/manage-repos
- google-github-actions/auth: https://github.com/google-github-actions/auth
