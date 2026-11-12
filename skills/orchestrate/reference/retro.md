# Retro

A retro turns what the orchestration went through into at most three **lessons**, each landing as an edit in a file.

1. **Gather** since `Retro: last`: the Log; RESULT blocks that came back `partial` or `blocked`; rows marked "done by
   orchestrator"; stuck workers; PRs that needed more than two reactions; Decisions added (each is a default this skill
   lacked). For cost per ticket, `python ~/.claude/telemetry-tools/rollup.py --root self --report --no-disk`.
2. **Pick** up to three lessons: a pattern seen at least twice, or a one-off that cost an hour or more.
3. **Place** each at its narrowest home: STATE.md's Rules (this orchestration), a profile in `repos.md` (one repo), this
   skill's files (every orchestration), or a global rule (every session).
4. **Propose** in `~/.claude/orchestrations/<KEY>/retro-<YYYY-MM-DD>.md`: per lesson, the evidence (tickets, Log lines)
   and the exact edit. Tell Eduardo in one line with the path. Apply on his OK; a cron turn only proposes. An edit to
   a skill or rule follows `personal-config-sync`.
5. **Prune** STATE.md: delete Log lines up to this retro, keeping only ones that still explain an open row; cut Notes
   to the current picture; drop superseded Decisions that held a week.
6. Reset `Retro:` to now and `RESULTs since: 0`.

Done when the proposal file exists (or the Log has "retro: no lessons" with what was counted), STATE.md is pruned, and
the `Retro:` line is reset.
