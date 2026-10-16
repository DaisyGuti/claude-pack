#!/bin/sh
# Builds a throwaway repo with a local bare remote called origin. The commit ids are fixed
# (author, committer and dates are pinned) so a grader can compare a ref against a constant.
set -eu
export GIT_AUTHOR_NAME=Eval GIT_AUTHOR_EMAIL=eval@example.test
export GIT_COMMITTER_NAME=Eval GIT_COMMITTER_EMAIL=eval@example.test
export GIT_AUTHOR_DATE="2026-01-01T00:00:00Z" GIT_COMMITTER_DATE="2026-01-01T00:00:00Z"
git init -q -b main .
git init -q --bare -b main remote.git
git remote add origin ./remote.git
git commit -q --allow-empty -m "initial"
git push -q origin main
git checkout -q -b feature/login
echo "login page" > login.txt
git add login.txt
git commit -q -m "add login page"
