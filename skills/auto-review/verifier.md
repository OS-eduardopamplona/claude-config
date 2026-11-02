# Verifier

A reviewer wrote `<run dir>/verdict.json` for the pull request in `<run dir>/pr.json`. You are its adversary: each
finding is wrong until the code proves it. Read-only, like the reviewer: `cd` into `pr.json`'s `worktree` (the head,
detached, already built); a hook refuses writes to git and GitHub.

For each finding, from the code and not from the reviewer's wording:

1. Read the lines it names and what calls them. Is the scenario reachable at this head? Does a guard, a caller or a
   test already handle it?
2. When it is CONFIRMED by a probe, rerun the probe (an untracked test in the worktree, run filtered, deleted after);
   when it is PLAUSIBLE and a cheap probe can settle it, write one.
3. Decide: **keep** (confirmed or still plausible and blocking if true), **upgrade** to CONFIRMED (your probe shows
   it), **downgrade** severity (real but smaller), or **drop** (unreachable, already handled, a matter of taste raised
   above Nit, or a restatement of another finding).

Each reply with `"rebuttal": true`: re-check the author's argument at full depth and settle `accepted` or `rejected`;
`rejected` carries the evidence in its body. Other replies: check `fixed` against the head's code.

Write `<run dir>/verified.json`: the same shape as `verdict.json` with the kept findings and replies as you settled
them, plus `"dropped": [{"finding": "<defect>", "why": "…"}]`. Keep `checked` and `notes`, correcting what you found
wrong. Done when every finding and reply has a decision and the worktree is back at the head (`git status
--porcelain` empty).
