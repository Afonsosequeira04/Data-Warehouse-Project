---
description: Run a project phase end-to-end up to the PR, then stop
---
Run phase: $ARGUMENTS

1. Run the automatic Post-merge cleanup from AGENTS.md for any leftover merged phase or chore branch (start with git fetch origin --prune). Then make sure you are on an up-to-date main with a clean working tree; if not, tell me and STOP.
2. Read AGENTS.md and ONLY the $ARGUMENTS section of
   docs/NOTION_PROJECT_PLAN.md.
3. Show: current repo state, files you expect to touch, open ADRs or decisions
   that block you. Wait for my OK before editing.
4. After my OK: create the phase branch from main, do the work, run the
   narrowest verification, commit following the repo's Git conventions, push
   the branch, and open the PR against main (gh pr create). If gh is
   unavailable, give me the exact PR title and body instead.
5. Do not merge. Do not start the next phase. Do not make decisions that
   AGENTS.md reserves for me.
6. Finish with the PHASE COMPLETION SUMMARY defined in AGENTS.md, then STOP.