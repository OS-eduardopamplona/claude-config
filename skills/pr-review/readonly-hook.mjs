import fs from "node:fs";

const DENY = [
  [/\bgit\b(\s+-C\s+\S+)*\s+(push|commit|merge|rebase|reset|tag|cherry-pick|revert|stash|switch|branch|worktree|am|apply|update-ref)\b(?!-)/, "the reviewer never writes to git history or refs; restore files with git checkout <sha> -- <paths>"],
  [/\bgit\b(\s+-C\s+\S+)*\s+checkout\s+(-b|-B|--orphan)\b/, "git checkout: the path form only (git checkout <sha> -- <paths>)"],
  [/\bgh\s+(pr\s+(review|merge|close|edit|ready|comment|reopen|create)|issue\s+(comment|edit|close|create)|release|repo\s+(edit|delete))\b/, "the reviewer reads GitHub; posting is the publisher's job"],
  [/\bgh\s+api\b(?=.*(-X|--method)\s*(POST|PATCH|PUT|DELETE))/i, "gh api: reads only"],
  [/\bgh\s+api\s+(?!graphql)\S*(?=.*\s(-f|-F|--field|--raw-field|--input)\s)/, "gh api with fields is a POST; reads only"],
  [/\bmutation\b/, "GraphQL mutations are the publisher's job"],
  [/auto-review\.mjs\s+(post|unlock|lock|queue|take)\b/, "posting and the run lock belong to the calling session, not a reviewer"],
  [/pr-review\.mjs\s+prepare\b/, "preparing a run belongs to the calling session, not a reviewer"],
];

const input = JSON.parse(fs.readFileSync(0, "utf8"));
const command = String(input.tool_input?.command ?? "");
const hit = DENY.find(([re]) => re.test(command));
if (hit) {
  console.log(JSON.stringify({ hookSpecificOutput: { hookEventName: "PreToolUse", permissionDecision: "deny", permissionDecisionReason: `the PR reviewer is read-only: ${hit[1]} (${command.slice(0, 100)})` } }));
}
