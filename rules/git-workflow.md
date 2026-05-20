# Git Workflow

## Worktrees
- Always branch from `master` (or main): `git worktree add ../Worktrees/<branch-name> -b <branch-name> master`
- After creating, switch working directory to the worktree. Do not modify files in the main repo.
- When asked to update a branch from master/main, always `git pull` in the main repo first to get the latest remote changes, then merge into the worktree branch.

## Committing
- If pre-commit hooks fail, fix the reported issue and retry. **NEVER bypass hooks by any mechanism** (`--no-verify`, deleting `.husky`/hook configs, env var overrides) unless Eduardo says so.
- Always run `git branch --show-current` before committing to verify the correct branch.

## Signing
- **NEVER use `--no-gpg-sign`**, period. If `git commit` fails to sign (YubiKey not touched, `gpg-agent` stalled, key unavailable), stop and tell Eduardo — do not retry with the flag.
- A one-time go-ahead to skip signing applies to **that single commit only**. Subsequent commits go back to signed; re-ask if signing fails again.
- Same rule for `-c commit.gpgsign=false` and any equivalent env-var override.
