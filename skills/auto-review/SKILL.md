---
name: auto-review
description: Eduardo's PR watcher and publisher for the team's OutSystems.Model, OutSystems.ModelExtensions and OutSystems.ModelQL PRs. Args: [dry-run] [deep] [owner/repo#n ...].
disable-model-invocation: true
---

# Auto-review

You run one watcher pass: you pick the PRs that are due, have each reviewed through the `pr-review` skill's flow, and
publish the result. You read no diff and touch no repository, worktree or PR yourself. [spec.md](spec.md) says what is
due and what gets posted; `C:/Users/U005017/.claude/skills/pr-review/CONTEXT.md` holds the vocabulary.

`ar` below means `node C:/Users/U005017/.claude/skills/auto-review/auto-review.mjs`, run with Bash from your session's
folder, never from inside `C:/git/ar-*`. Your args: optional `dry-run` and `deep`, then PRs (`owner/repo#n` or URLs).
No PRs means a scheduled pass.

1. **Lock.** `ar lock` prints a token; keep it. Exit 3 means another pass holds the lock:
   - No PRs: report "another run is in progress" and stop.
   - PRs: `ar queue <options> <PRs>`, then `ar lock` once more. Exit 3 again: report them queued behind that pass and
     stop. A token: go on with an empty list; `ar take` in step 3 returns your PRs.
2. **List.** PRs: `ar next --force <options> <PRs>`. Scheduled: `ar next`. Each stdout line is one round,
   `<PR> <round> <lastHead> <requested> [dry-run] [deep]`; stderr names skipped PRs.
3. **Review and publish.** Before each line of your list, and once more when the list is done, run `ar take`: its
   lines are PRs someone named while you ran, and go first. For each line, one PR at a time:
   1. `ar lock <token>` renews the lock. Exit 3: the lock was lost; treat it as a failure.
   2. Read `C:/Users/U005017/.claude/skills/pr-review/SKILL.md` and run its steps 1 to 3 for `<PR> <round> <lastHead>`
      (with `--deep` for `deep`, without `--chat`).
   3. `ar post <dir> --requested <requested>`, plus `--dry-run` for `dry-run`. Keep the URL it prints.

   A failed step: `ar alert "Auto-review: a review run failed" "<PR>: <step> failed (<dir>)"`, then skip the rest of the
   list and go to step 4.
4. **Unlock.** `ar unlock <token>`. Exit 4 means PRs were queued meanwhile: review what `ar take` prints as in step 3,
   then unlock again.
5. **DM.** `ar` notifies Eduardo's Slack workflow itself and prints `DM: <text>` only when it could not. Every such line
   is a Slack message to Eduardo: send `<text>` with the Slack connector's `slack_send_message` (load it with
   ToolSearch), `channel_id` `U09RXPNJ9C6`. Send each as it appears.
6. **Report** in at most eight lines: each PR (repo#number, round, the posted URL, the dry-run's `post.md`, or the
   failure), "nothing due", or that the PRs were queued.

Reviews run one at a time: wait for each agent's notification without polling. A PR named by hand is reviewed as its
next round whether or not it was re-requested. Never approve a PR, and post only through `ar post`.
