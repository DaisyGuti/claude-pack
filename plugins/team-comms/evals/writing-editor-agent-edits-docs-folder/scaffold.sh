#!/bin/sh
# Builds the throwaway repo this case runs in. Needs --scaffold.
set -e
git init -q -b main .
mkdir -p docs
cat > docs/deploy.md <<'EOF'
# Deploying

In order to deploy, you should leverage the pipeline, which seamlessly handles the rollout. It is worth noting that a deploy takes about 12 minutes.
EOF
cat > docs/rollback.md <<'EOF'
# Rolling back

It's important to understand that rolling back is a crucial part of our robust process. Run `helm rollback web 41` to go back one release.
EOF
cat > docs/oncall.md <<'EOF'
# On-call

The on-call engineer is the person who is on call. Pages go to the #oncall channel and should be acknowledged within 15 minutes.
EOF
