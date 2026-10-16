#!/bin/sh
# Builds the throwaway repo this case runs in. Needs --scaffold.
set -e
git init -q -b main .
mkdir -p docs
printf '# Public API gateway\n\nEnvoy-based gateway on GKE in front of the form-intake service.\n' > docs/README.md
git add -A
git -c user.email=dev@example.com -c user.name=Dev commit -q -m init
