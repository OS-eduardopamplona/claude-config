# CLAUDE.md Local Policy (OutSystems.Model)

- In the OutSystems.Model repo, CLAUDE.md learnings stay local for now: when creating or editing a CLAUDE.md (e.g. via the capture-learnings or capture-context skills), add its path to `.git/info/exclude` instead of committing it.
- This overrides the capture-learnings skill's commit step in that repo — report entries as "added locally" and still release the PR gate normally.
- If the team later decides to share CLAUDE.md files, remove the exclude entries and commit them through a PR.
