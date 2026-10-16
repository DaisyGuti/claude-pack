#!/bin/sh
# Builds the throwaway repo this case runs in. Needs --scaffold.
set -e
git init -q -b main .
mkdir -p docs/decisions
printf -- '---\nstatus: "accepted"\ndate: 2026-01-05\n---\n\n# Use DynamoDB for the audit log\n\n## Context and Problem Statement\n\nPick a store.\n' > docs/decisions/0001-use-dynamodb.md
