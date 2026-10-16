#!/bin/sh
# Builds the throwaway repo this case runs in. Needs --scaffold.
set -e
git init -q -b main .
mkdir -p docs/rfcs
printf '# Caching layer\n\n## Problem\n\nReads are slow.\n' > docs/rfcs/0001-caching-layer.md
