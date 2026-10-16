# Enforcing signatures with Binary Authorization

Contents:
- What Binary Authorization can check
- Pick an enforcement path
- Path A: attestor with a KMS key
- Path B: Sigstore signature check
- Path C: keyless verification inside the cluster
- Rollout order
- Sources

Binary Authorization is a deploy-time control on production workloads. Draft policy and
commands, show them, and let the user apply them. Start every policy in dry-run mode.

## What Binary Authorization can check

Binary Authorization enforces that images deployed to GKE, Cloud Run, Cloud Service Mesh and
Google Distributed Cloud conform to a policy. Its platform policies offer these check types:
simple signing attestation check, Sigstore signature check, SLSA check, trusted directory
check and vulnerability check. Fetch the current overview before relying on this list:
https://docs.cloud.google.com/binary-authorization/docs/overview

Two limits shape the choice of path:

- The Sigstore signature check takes public keys (a Cloud KMS key or a cosign key pair) in its
  policy. The documentation does not describe keyless identity matching for it.
- The SLSA check supports Cloud Build as its only trusted builder and is in Preview. Images
  built on GitHub Actions or GitLab CI do not satisfy it.

## Pick an enforcement path

| Path | Signer | Enforced by | Use when |
|---|---|---|---|
| A. Attestor with KMS key | Pipeline creates an attestation with a KMS key | Binary Authorization on GKE or Cloud Run | The customer wants Google's own deploy gate on Cloud Run or GKE |
| B. Sigstore signature check | `cosign sign --key gcpkms://...` | Binary Authorization continuous validation on GKE | Pods already running must keep conforming |
| C. Keyless in-cluster | cosign keyless identity | Sigstore policy-controller (or Kyverno) running in GKE | You want identity-pinned keyless verification and accept running the admission controller |

Paths A and B need a KMS signing step beside the keyless one. Add it to the pipeline after
the image is pushed, using the same Workload Identity Federation identity with
`roles/cloudkms.signerVerifier` on the one key.

## Path A: attestor with a KMS key

```sh
# One time, by a human. Names are examples.
gcloud kms keyrings create binauthz --location=LOCATION
gcloud kms keys create build-attestor --keyring=binauthz --location=LOCATION \
  --purpose=asymmetric-signing --default-algorithm=ec-sign-p256-sha256

# The attestor points at a Container Analysis note that must already exist. Create the note
# by following the attestor documentation current at run time; the call is not reproduced
# here because it was not verified in this build.
gcloud container binauthz attestors create build-attestor \
  --attestation-authority-note=NOTE_ID --attestation-authority-note-project=PROJECT
gcloud container binauthz attestors public-keys add \
  --attestor=build-attestor \
  --keyversion-project=PROJECT --keyversion-location=LOCATION \
  --keyversion-keyring=binauthz --keyversion-key=build-attestor --keyversion=1

# In the pipeline, after the push:
gcloud container binauthz attestations sign-and-create \
  --artifact-url="LOCATION-docker.pkg.dev/PROJECT/REPOSITORY/IMAGE@sha256:..." \
  --attestor=build-attestor --attestor-project=PROJECT \
  --keyversion-project=PROJECT --keyversion-location=LOCATION \
  --keyversion-keyring=binauthz --keyversion-key=build-attestor --keyversion=1
```

The artifact URL must name the digest. Check each flag against the current gcloud reference
(https://docs.cloud.google.com/sdk/gcloud/reference/beta/container/binauthz/attestations/sign-and-create)
before running; the command group is under `beta` and `alpha` in some releases.

Policy, exported with `gcloud container binauthz policy export` and imported with
`gcloud container binauthz policy import POLICY.yaml`:

```yaml
globalPolicyEvaluationMode: ENABLE
defaultAdmissionRule:
  evaluationMode: REQUIRE_ATTESTATION
  enforcementMode: DRYRUN_AUDIT_LOG_ONLY   # change to ENFORCED_BLOCK_AND_AUDIT_LOG after the dry run
  requireAttestationsBy:
    - projects/PROJECT/attestors/build-attestor
```

Cloud Run: enable the check on a service with
`gcloud run services update SERVICE --binary-authorization=default`. GKE: enable Binary
Authorization on the cluster. Both use the project's policy.

## Path B: Sigstore signature check

Sign with the KMS key:

```sh
cosign sign --key gcpkms://projects/PROJECT/locations/LOCATION/keyRings/RING/cryptoKeys/KEY "$IMAGE@$DIGEST"
```

Create a platform policy whose `sigstoreSignatureCheck` lists the key's public key (PEM) and
apply it with `gcloud beta container binauthz policy create POLICY_ID --platform=gke
--policy-file=POLICY_PATH --project=PROJECT`. The schema is under `gkePolicy.checkSets[].checks[]`
with `sigstoreSignatureCheck.sigstoreAuthorities[].publicKeySet.publicKeys`. Fetch the page in
Sources for the exact YAML.

## Path C: keyless verification inside the cluster

The Sigstore policy-controller is a Kubernetes admission controller that verifies Sigstore
signatures and attestations. Its `keyless` authorities match an OIDC issuer and a subject
(`subjectRegExp` allows patterns), which maps to the identity table in `sign-and-attest.md`.
Write the subject as narrowly as the exact workflow. It is software the team runs, so plan
its upgrades and its own availability.

## Rollout order

1. Sign and attest in the pipeline for every image, with enforcement off.
2. Switch the policy to dry run and read the audit log for would-be denials.
3. Fix the denials: unsigned images, other registries, system images.
4. Enable enforcement for one non-production namespace or service.
5. Enable it for production, with a documented break-glass procedure and an owner.

## Sources

Fetched 2026-10-16.

- Binary Authorization overview: https://docs.cloud.google.com/binary-authorization/docs/overview
- Sigstore signature check: https://docs.cloud.google.com/binary-authorization/docs/cv-sigstore-check
- SLSA check: https://docs.cloud.google.com/binary-authorization/docs/cv-slsa-check
- Policy YAML reference: https://docs.cloud.google.com/binary-authorization/docs/policy-yaml-reference
- Binary Authorization for Cloud Run: https://docs.cloud.google.com/binary-authorization/docs/run/enabling-binauthz-cloud-run
- attestors create: https://docs.cloud.google.com/sdk/gcloud/reference/container/binauthz/attestors/create
- attestors public-keys add: https://docs.cloud.google.com/sdk/gcloud/reference/container/binauthz/attestors/public-keys/add
- sign-and-create reference: https://docs.cloud.google.com/sdk/gcloud/reference/beta/container/binauthz/attestations/sign-and-create
- Sigstore policy-controller: https://docs.sigstore.dev/policy-controller/overview/
