#!/bin/sh
# Builds the throwaway repo this case runs in. Needs --scaffold.
set -e
git init -q -b main .
git config user.email dev@example.com
git config user.name Dev
git remote add origin https://git.example.gov/team/upload.git
WHEN=$(python3 -c "from datetime import datetime, timedelta; print((datetime.now().astimezone() - timedelta(days=1, hours=1)).isoformat())")
echo "Add retry with backoff to upload client" >> work.txt
git add work.txt
GIT_AUTHOR_DATE="$WHEN" GIT_COMMITTER_DATE="$WHEN" git commit -q -m "Add retry with backoff to upload client"
WHEN=$(python3 -c "from datetime import datetime, timedelta; print((datetime.now().astimezone() - timedelta(days=1, hours=1)).isoformat())")
echo "Add tests for upload retry" >> work.txt
git add work.txt
GIT_AUTHOR_DATE="$WHEN" GIT_COMMITTER_DATE="$WHEN" git commit -q -m "Add tests for upload retry"
WHEN=$(python3 -c "from datetime import datetime, timedelta; print((datetime.now().astimezone() - timedelta(days=1, hours=1)).isoformat())")
echo "Fix timeout default in upload config" >> work.txt
git add work.txt
GIT_AUTHOR_DATE="$WHEN" GIT_COMMITTER_DATE="$WHEN" git commit -q -m "Fix timeout default in upload config"
