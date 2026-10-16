#!/bin/sh
# Verify a container image signature, and optionally an attestation, against a signer identity.
#
# Usage:
#   verify_image.sh --host github|gitlab --identity IDENTITY [--issuer URL] [--attestation TYPE] IMAGE
#   verify_image.sh --key KEYREF [--attestation TYPE] IMAGE
#
# IMAGE must be a digest reference (registry/repo@sha256:...). Keyless verification always
# pins both the signer identity and the OIDC issuer; a signature from any other identity
# fails. IDENTITY is written out in full, for example:
#   GitHub  https://github.com/ORG/REPO/.github/workflows/secure-build.yml@refs/heads/main
#   GitLab  https://gitlab.com/GROUP/PROJECT//.gitlab-ci.yml@refs/heads/main
# (GitLab uses a double slash before the CI file path.) --issuer defaults to GitHub's
# https://token.actions.githubusercontent.com and to https://gitlab.com; pass it for a
# self-managed GitLab. TYPE is a cosign attestation type such as cyclonedx, spdxjson or
# slsaprovenance.

set -eu

HOST=""
IDENTITY=""
ISSUER=""
KEY=""
ATTESTATION=""

die() {
    echo "verify_image.sh: $1" >&2
    exit 2
}

while [ $# -gt 0 ]; do
    case "$1" in
        --host) [ $# -ge 2 ] || die "--host needs github or gitlab."; HOST=$2; shift 2 ;;
        --identity) [ $# -ge 2 ] || die "--identity needs a value."; IDENTITY=$2; shift 2 ;;
        --issuer) [ $# -ge 2 ] || die "--issuer needs a URL."; ISSUER=$2; shift 2 ;;
        --key) [ $# -ge 2 ] || die "--key needs a cosign key reference such as gcpkms://..."; KEY=$2; shift 2 ;;
        --attestation) [ $# -ge 2 ] || die "--attestation needs a type."; ATTESTATION=$2; shift 2 ;;
        -h | --help) sed -n '2,20p' "$0"; exit 0 ;;
        -*) die "unknown option $1. Run with --help." ;;
        *) break ;;
    esac
done

[ $# -eq 1 ] || die "expected exactly one IMAGE. Run with --help."
IMAGE=$1

case "$IMAGE" in
    *@sha256:*) ;;
    *) die "'$IMAGE' is not a digest reference. Resolve it first: docker buildx imagetools inspect $IMAGE" ;;
esac

command -v cosign >/dev/null 2>&1 || die "cosign is not installed. Install it from https://docs.sigstore.dev/cosign/system_config/installation/ and rerun."

if [ -n "$KEY" ]; then
    [ -z "$IDENTITY" ] && [ -z "$HOST" ] || die "--key cannot be combined with --identity or --host."
    set -- --key "$KEY"
else
    [ -n "$IDENTITY" ] || die "keyless verification needs --identity (the exact signer identity)."
    case "$IDENTITY" in
        *'*'*) die "identity '$IDENTITY' contains a wildcard. Write the full identity of the one workflow allowed to sign." ;;
    esac
    case "$HOST" in
        github) [ -n "$ISSUER" ] || ISSUER=https://token.actions.githubusercontent.com ;;
        gitlab)
            [ -n "$ISSUER" ] || ISSUER=https://gitlab.com
            case "$IDENTITY" in
                *//*//*) ;;
                *) die "GitLab identities put a double slash before the CI file path (https://gitlab.com/GROUP/PROJECT//.gitlab-ci.yml@refs/heads/main)." ;;
            esac
            ;;
        *) die "--host must be github or gitlab." ;;
    esac
    set -- --certificate-identity "$IDENTITY" --certificate-oidc-issuer "$ISSUER"
fi

cosign verify "$@" "$IMAGE"
if [ -n "$ATTESTATION" ]; then
    cosign verify-attestation --type "$ATTESTATION" "$@" "$IMAGE"
fi
