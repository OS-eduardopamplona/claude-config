---
name: review-now
description: Start Eduardo's auto-reviewer on specific PRs right away, or queue them behind the run in progress. Args: [dry-run] [deep] <owner/repo#n | GitHub PR URL>...
disable-model-invocation: true
---

# Review now

Read `C:/Users/U005017/.claude/skills/auto-review/SKILL.md` and follow it here, in this session, with these args as
given. With no run in progress it reviews the PRs one after the other; with a run in progress it queues them and that
run reviews them next.

A PR whose head is already reviewed is reviewed again as the next round, which is how a rebuttal without a new commit
gets its answer. `dry-run` posts nothing; `deep` adds the build, red/green and probe tests for that PR.
