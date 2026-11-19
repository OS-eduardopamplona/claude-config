---
name: auto-review
description: Eduardo's automated PR reviewer for the team's OutSystems.Model, OutSystems.ModelExtensions and OutSystems.ModelQL PRs. Args: [dry-run] [deep] [owner/repo#n ...].
disable-model-invocation: true
---

# Automated PR review

You run one review pass. You are the orchestrator: you pick PRs, hand each to a reviewer subagent, post, and DM
Eduardo. The subagents review; you read no diff and touch no repository, worktree or PR yourself. [spec.md](spec.md)
says what the reviewer does.

`ar` below means `node C:/Users/U005017/.claude/skills/auto-review/auto-review.mjs`, run with Bash from your session's
folder, never from inside `C:/git/ar-*`. Your args: optional `dry-run` and `deep`, then PRs (`owner/repo#n` or URLs).
No PRs means a scheduled pass.

1. **Lock.** `ar lock` prints a token; keep it. Exit 3 means another pass holds the lock:
   - No PRs: report "another run is in progress" and stop.
   - PRs: `ar queue <options> <PRs>`, then `ar lock` once more. Exit 3 again: report them queued behind that pass and
     stop. A token: go on with an empty list; `ar take` in step 3 returns your PRs.
2. **List.** PRs: `ar next --force <options> <PRs>`. Scheduled: `ar next`. Each stdout line is one review,
   `<PR> <round> <lastHead> [dry-run] [deep]`; stderr names skipped PRs.
3. **Review.** Before each line of your list, and once more when the list is done, run `ar take`: its lines are PRs
   someone named while you ran, and go first. For each line, one PR at a time:
   1. `ar lock <token>` renews the lock. Exit 3: the lock was lost; treat it as a failure.
   2. `ar prepare <PR> <round> <lastHead>` (add `--deep` for `deep`) prints the run dir.
   3. Reviewer: the Agent tool with `subagent_type` `general-purpose`, `model` `opus`, `effort` `xhigh`, prompt
      `Read C:/Users/U005017/.claude/skills/auto-review/reviewer.md and follow it. Run dir: <dir>.`, plus ` Deep.` for
      `deep`. Wait for its completion notification, then `ar validate <dir>/verdict.json` must print `valid`.
   4. `ar needs-verify <dir>` prints `skip`, `verify` or `max`. `skip`: copy `verdict.json` to `verified.json`.
      Otherwise a verifier the same way with `verifier.md`, `effort` `max` on `max` and left out on `verify`; then
      `ar validate <dir>/verified.json` must print `valid`.
   5. `ar post <dir>`, with `--dry-run` for `dry-run`. Keep the URL it prints.
   
   A failed step (non-zero exit, `validate` not printing `valid`, a subagent that ended without writing its file):
   `ar alert "Auto-review: a review run failed" "<PR>: <step> failed (<dir>)"`, then skip the rest of the list and go
   to step 4.
4. **Unlock.** `ar unlock <token>`. Exit 4 means PRs were queued meanwhile: review what `ar take` prints as in step 3,
   then unlock again.
5. **DM.** Every `DM: <text>` line an `ar` command printed is a Slack message to Eduardo: send `<text>` with the Slack
   connector's `slack_send_message` (load it with ToolSearch), `channel_id` `U09RXPNJ9C6`. Send each as it appears.
6. **Report** in at most eight lines: each PR (repo#number, round, the posted URL, the dry-run's `post.md`, or the
   failure), "nothing due", or that the PRs were queued.

Subagents run one at a time: wait for each notification without polling and start the next step only after it. A PR
whose head is already reviewed and is named again is reviewed as the next round, which is how a rebuttal without a new
commit gets its answer. Never approve a PR, and post only through `ar post`.
