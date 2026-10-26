# Customer data

- Customer apps and OMLs are read in place. Never copy them into a git folder, a test, a fixture or an artifact; outputs stay under the scratchpad and are deleted when the task ends.
- No customer name in anything that leaves the machine: commits, pushed branch names, PR titles and bodies, ADRs, READMEs, tests, reports and Slack drafts. Say "the customer app"; name its elements generically ("a library block", "a data action"). Jira summaries may carry the name the tracker already uses.
- Local worktree names and untracked scratch folders may carry the name. The denylist the commit hook enforces lives in `~/.claude/customer-names.txt`, one name or prefix per line, outside the config repo.
