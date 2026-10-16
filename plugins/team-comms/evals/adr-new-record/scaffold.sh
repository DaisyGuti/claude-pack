#!/bin/sh
# Builds the throwaway repo this case runs in. Needs --scaffold.
set -e
git init -q -b main .
mkdir -p docs/adr
printf -- '---\nstatus: "accepted"\ndate: 2026-01-05\n---\n\n# Use Python\n\n## Context and Problem Statement\n\nPick a language.\n' > docs/adr/0001-use-python.md
printf -- '---\nstatus: "accepted"\ndate: 2026-02-01\n---\n\n# Use GCP\n\n## Context and Problem Statement\n\nPick a cloud.\n' > docs/adr/0002-use-gcp.md
