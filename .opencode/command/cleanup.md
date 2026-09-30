---
description: Sync local repo with GitHub after a phase PR was merged
---
Clean up after phase: $ARGUMENTS

Run `bash scripts/cleanup.sh $ARGUMENTS` and show its full output. Do NOT run any other git command first. Do NOT state whether a PR is merged or open yourself: the script decides. If it exits with an error, show the message and STOP.