---
name: review-now
description: Start Eduardo's auto-reviewer on specific PRs right away, or queue them behind the run in progress. Args: [dry-run] [deep] <owner/repo#n | GitHub PR URL>...
disable-model-invocation: true
---

# Review now

Read `C:/Users/U005017/.claude/skills/auto-review/SKILL.md` and follow it here, in this session, with these args as
given. With no run in progress it reviews the PRs one after the other; with a run in progress it queues them and that
run reviews them next.

A named PR is reviewed as its next round and posted whether or not its author re-requested Eduardo. To review without
posting, use `/pr-review`. `dry-run` posts nothing; `deep` adds the build, red/green and probe tests for that PR.
