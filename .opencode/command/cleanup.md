---
description: Sync local repo with GitHub after a phase PR was merged
---
Clean up after phase: $ARGUMENTS

Goal: local repo identical to GitHub main, with the phase branch removed.

1. Find the phase branch and its PR (gh pr list --state all, or git branch).
   Confirm the PR is MERGED (gh pr view --json state,mergedAt). If it is not
   merged, STOP and tell me.
2. If the working tree has uncommitted changes, show them and STOP. Never
   discard changes without asking me.
3. git checkout main && git fetch origin --prune &&
   git pull --ff-only origin main
4. Delete the local phase branch with git branch -d. If it refuses because the
   PR was squash-merged, show me why and ask before using -D. Delete the
   remote branch only if GitHub did not already do it.
5. Verify: git status is clean, git rev-parse HEAD equals
   git rev-parse origin/main, no leftover phase branches locally or remotely.
6. Never use reset --hard, force push, or touch any other branch.

Report in short form: PR merged (yes/no), branches deleted, HEAD commit, sync
status. Then STOP.