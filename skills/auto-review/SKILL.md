---
name: auto-review
description: Eduardo's automated PR reviewer for the team's OutSystems.Model, OutSystems.ModelExtensions and OutSystems.ModelQL PRs. Args: [dry-run] [deep] [owner/repo#n ...].
disable-model-invocation: true
---

# Automated PR review

Run `bash C:/Users/U005017/.claude/skills/auto-review/run.sh <args>` with `run_in_background: true`, then wait for its
completion notification and report its output: one line per PR (reviewed, queued, nothing to review, or failed with
its log).

`run.sh` is the whole reviewer; [spec.md](spec.md) says what it does. Per PR it runs `auto-review.mjs prepare`, one
headless Opus following [reviewer.md](reviewer.md), a verifier following [verifier.md](verifier.md) only when the
verdict blocks or settles a rebuttal, then `auto-review.mjs post`. With no PRs named it reviews up to 4 due PRs; with
PRs named it reviews those; while another run holds the lock it queues them in `~/.claude/auto-review/requested.txt`
for that run. `dry-run` posts nothing (`post.md` in the run dir); `deep` adds the build, red/green and probe tests.
