# Git & PRs

## Branches
- Always branch from `master` (or main): `git checkout -b <branch-name> master` unless Eduardo instructs otherwise.
- When asked to update a branch from master/main, always `git pull` on master first to get the latest remote changes, then merge into the branch.

## Merging master
- Merge master into a PR branch only when GitHub reports a conflict or the branch needs something from master, never ahead of time.
- Run `git merge origin/master` on the branch, so the branch is the first parent. Master as first parent leaves GitHub's stored PR base stale: the PR lists master's commits and requests reviews from their code owners.
- Resolve a conflict keeping both sides whole; size the check to it: build plus the tests the conflicting files feed, full suite only when code paths merged.
- Shared append-lists (test-case registries, CLAUDE.md notes, sweep parameters) are conflict hotspots; when one conflicts twice, raise splitting it.
- Before merging a batch of PRs that land side by side, check they work together: two PRs that each add the same member merge cleanly and break master's compile. Merge every head onto master in a scratch commit (`git merge-tree --write-tree`, then `git commit-tree`), check the pairs for shared files and shared new declarations, build that commit once, and run the test classes the batch changes. If clean, merge each PR at its green head.

## Committing
- Leave changes local and unstaged. Only stage/commit/push when Eduardo asks.
- Separate commits for separate concerns — never bundle independent changes (e.g. API exposure vs serialization fix) into one commit, even within one PR. Split mixed files across commits when needed.
- If pre-commit hooks fail, fix the reported issue and retry. **NEVER bypass hooks by any mechanism** (`--no-verify`, deleting `.husky`/hook configs, env var overrides) unless Eduardo says so.
- Always run `git branch --show-current` before committing to verify the correct branch.

## Signing
- **NEVER use `--no-gpg-sign`**, period. If `git commit` fails to sign (YubiKey not touched, `gpg-agent` stalled, key unavailable), stop and tell Eduardo — do not retry with the flag.
- A one-time go-ahead to skip signing applies to **that single commit only**. Subsequent commits go back to signed; re-ask if signing fails again.
- Same rule for `-c commit.gpgsign=false` and any equivalent env-var override.

## Commit messages & PR descriptions
- Keep short: subject + minimal why-focused body; a few lines, not exhaustive change lists.
- Write commit message bodies and PR descriptions compressed: drop articles, filler, and hedging; keep all technical substance.
- Repo conventions still win: subject lines keep the Jira-tag style (`RDMST-xxxx Description`), not Conventional Commits prefixes, and PR descriptions keep the repo's PR template structure — compress the content inside the sections.

## Pull requests
- Always create PRs as drafts (`--draft` flag).
- Always use the PR template for descriptions.
- Always prefix branch names and PR titles with a Jira tag. Default to `RDMST-0000` if none provided.
- Add @OS-eduardopamplona to assignees (GitHub login; `EduardoPamplona` fails).
- Keep PR descriptions in sync with commits on Eduardo-owned PRs. Don't edit PRs owned by others.
- When work is split across PRs and one needs another's changes, make them a GitHub stack ([docs](https://docs.github.com/en/pull-requests/get-started/about-stacked-prs)), not just a PR based on another's branch. Use the `github/gh-stack` extension (`gh extension install github/gh-stack`): `gh stack link <bottom-pr> <next-pr> ...`, listed bottom to top, for PRs that already exist. It fixes the PRs' bases and is idempotent. Stacks are same-repo only.
- Stack PRs in a straight line: two PRs on one parent get one stacked on the other. A PR with auto-merge on cannot join a stack.
- Keep a stack current: before any merge, check whether GitHub reports it out of date with master; if so, cascade signed merges up it (master into the bottom branch, then each layer into the next).
- Merge a stack from its top once every PR is approved and green (`gh stack merge <stack> --squash`).
- Keep descriptions succinct: a one-line problem statement plus short bullets of what changed; no test narration, design rationale or per-file walkthrough. Over ~8 lines is too long.
- When addressing review comments, resolve the thread. Reply first only when the reviewer is an agent: one line saying what changed. A person's thread gets no reply.
- Never edit a posted PR comment; reply in the thread or add a new comment, and only when needed.
- When reviewing a PR, run `gh pr checks` and state the result (pass / fail / not run).
- A PR marked ready takes no new scope: only review responses, conflict merges and CI fixes. New fixes go to a follow-up draft PR based on its branch.
- Before marking a PR ready, run a whole-PR `/code-review` at high effort, in parallel with CI rather than after it.
- The `minor` and `patch` label is only valid for the OutSystems.Model repo. For other repos, check available labels with `gh label list` first.
