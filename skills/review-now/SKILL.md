---
name: review-now
description: Start Eduardo's auto-reviewer on specific PRs right away, or queue them behind the run in progress. Args: [dry-run] [deep] <owner/repo#n | GitHub PR URL>...
disable-model-invocation: true
---

# Review now

1. Run `bash C:/Users/U005017/.claude/skills/auto-review/run.sh <args>` with `run_in_background: true`, passing the
   args as given. With no run in progress it reviews the PRs one after the other, printing
   `<PR> round <n>: reviewing, log <file>` as each starts. With a run in progress it prints `<PR>: queued behind the run
   in progress` and exits; that run reviews them next.
2. Tell Eduardo from the first lines whether the PRs started or were queued, then end the turn. Do not poll.
3. When the background command finishes, report one line per PR from its output: `done`, `nothing to review` or the
   failure (already DMed on Slack). The posted review's URL is in the output after `post`.

A PR whose head is already reviewed is reviewed again as the next round, which is how a rebuttal without a new commit
gets its answer. `dry-run` posts nothing; `deep` adds the build, red/green and probe tests for that PR.
