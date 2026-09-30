#!/usr/bin/env bash
set -euo pipefail
branch="${1:?usage: scripts/cleanup.sh <branch>}"
if [ "$branch" = "main" ]; then echo "Refusing to clean main."; exit 1; fi
git fetch origin --prune
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "Working tree has tracked changes. Nothing done:"; git status --short; exit 1
fi
if git show-ref --verify --quiet "refs/heads/$branch"; then
  if ! git merge-base --is-ancestor "$branch" origin/main; then
    echo "NOT MERGED into origin/main (or squash/rebase-merged). Nothing deleted."; exit 1
  fi
else
  echo "Local branch $branch does not exist."
fi
git switch main
git pull --ff-only origin main
if git show-ref --verify --quiet "refs/heads/$branch"; then git branch -d "$branch"; fi
if git ls-remote --exit-code --heads origin "$branch" >/dev/null 2>&1; then git push origin --delete "$branch"; fi
git status -sb
if [ "$(git rev-parse main)" = "$(git rev-parse origin/main)" ]; then echo "main == origin/main"; else echo "WARNING: main differs from origin/main"; fi
git branch -a
git log --oneline -5