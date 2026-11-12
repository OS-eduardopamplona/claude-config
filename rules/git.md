# Git & PRs

## Branches
- Always branch from `master` (or main): `git checkout -b <branch-name> master` unless Eduardo instructs otherwise.
- When asked to update a branch from master/main, always `git pull` on master first to get the latest remote changes, then merge into the branch.

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
- The `minor` and `patch` label is only valid for the OutSystems.Model repo. For other repos, check available labels with `gh label list` first.
