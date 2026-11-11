---
name: review-now
description: Start Eduardo's auto-reviewer on specific PRs right away, even while the scheduled loop is mid-batch. Args: [dry-run] [no-red-green] <owner/repo#n | GitHub PR URL>...
disable-model-invocation: true
---

# Review now

1. Run `bash C:/Users/U005017/.claude/skills/auto-review/now.sh <args>` with `run_in_background: true`, passing the
   args as given. It prints one line per PR it started (`<PR>: slot <n>, log <file>`) and refuses a PR another run is
   already reviewing (`already being reviewed`).
2. Tell Eduardo, from the first lines of its output, which PRs started and which were refused, then end the turn. A
   Model review can take hours; do not poll.
3. When the background command finishes, report one line per PR: `finished` or `failed`, with its log. A failed run has
   already DMed Eduardo on Slack (`check-run --now`). The posted review's URL is in the log's last `result` line.

A PR whose head is already reviewed is reviewed again as the next round, on the same head, which is how a rebuttal the
author wrote without a new commit gets its answer; `dry-run` posts nothing.
