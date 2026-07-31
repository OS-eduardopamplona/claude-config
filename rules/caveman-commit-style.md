# Caveman Commits & PR Descriptions

- Separate commits for separate concerns — never bundle independent changes (e.g. API exposure vs serialization fix) into one commit, even within one PR. Split mixed files across commits when needed.
- Keep commit messages and PR descriptions short: subject + minimal why-focused body; a few lines, not exhaustive change lists.
- Write commit message bodies and PR descriptions in caveman full compression (invoke the `caveman:caveman-commit` skill for commits when available): drop articles, filler, and hedging; keep all technical substance.
- This overrides the caveman plugin boundary "Code/commits/PRs: write normal".
- Repo conventions still win over caveman defaults: subject lines keep the Jira-tag style (`RDMST-xxxx Description`), not Conventional Commits prefixes, and PR descriptions keep the repo's PR template structure — compress the content inside the sections.
