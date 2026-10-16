#!/bin/sh
# Collect vulnerability-scan and SBOM evidence for one container image.
#
# Usage: image_evidence.sh [--scanner trivy|grype] [--fail-on SEVERITY] [--allow-tag] IMAGE OUT_DIR
#
# Writes into OUT_DIR: trivy.json (or grype.json), sbom.cdx.json (CycloneDX) and
# sbom.spdx.json (SPDX), then prints a summary (summarize_evidence.py) and exits with its
# status. IMAGE must be a digest reference (registry/repo@sha256:...) so the evidence names
# one immutable image; --allow-tag overrides that for a quick local look.

set -eu

SCANNER=trivy
FAIL_ON=""
ALLOW_TAG=0
HERE=$(cd "$(dirname "$0")" && pwd)

die() {
    echo "image_evidence.sh: $1" >&2
    exit 2
}

while [ $# -gt 0 ]; do
    case "$1" in
        --scanner) [ $# -ge 2 ] || die "--scanner needs a value (trivy or grype)."; SCANNER=$2; shift 2 ;;
        --fail-on) [ $# -ge 2 ] || die "--fail-on needs a severity such as HIGH."; FAIL_ON=$2; shift 2 ;;
        --allow-tag) ALLOW_TAG=1; shift ;;
        -h | --help) sed -n '2,10p' "$0"; exit 0 ;;
        --) shift; break ;;
        -*) die "unknown option $1. Run with --help." ;;
        *) break ;;
    esac
done

[ $# -eq 2 ] || die "expected IMAGE and OUT_DIR. Run with --help."
IMAGE=$1
OUT=$2

case "$SCANNER" in
    trivy | grype) ;;
    *) die "--scanner must be trivy or grype, got '$SCANNER'." ;;
esac

case "$IMAGE" in
    *@sha256:*) ;;
    *)
        [ "$ALLOW_TAG" -eq 1 ] || die "'$IMAGE' is not a digest reference. Resolve it with: docker buildx imagetools inspect $IMAGE (or pass --allow-tag for a local look)."
        echo "warning: scanning a tag; the result describes whatever the tag pointed to just now." >&2
        ;;
esac

for tool in "$SCANNER" syft python3; do
    command -v "$tool" >/dev/null 2>&1 || die "$tool is not installed. See the install page for $tool (https://github.com/anchore/syft, https://trivy.dev, https://github.com/anchore/grype) and rerun."
done

mkdir -p "$OUT"

if [ "$SCANNER" = trivy ]; then
    # Scan without a severity filter so the summary counts every finding; the gate is --fail-on.
    trivy image --format json --output "$OUT/trivy.json" --scanners vuln,secret "$IMAGE"
else
    grype "$IMAGE" -o json >"$OUT/grype.json"
fi
syft "$IMAGE" -o cyclonedx-json="$OUT/sbom.cdx.json" -o spdx-json="$OUT/sbom.spdx.json"

if [ -n "$FAIL_ON" ]; then
    exec python3 "$HERE/summarize_evidence.py" --fail-on "$FAIL_ON" "$OUT"
fi
exec python3 "$HERE/summarize_evidence.py" "$OUT"
