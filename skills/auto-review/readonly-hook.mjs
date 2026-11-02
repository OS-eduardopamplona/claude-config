import fs from "node:fs";

const REVIEW_TREE = /(^|[\s"'=])(\/c|c:)?[\\/]git[\\/]ar-(model|mx|mql)\b/i;
const DENY = [
  [/\bgit\b(\s+-C\s+\S+)*\s+(push|commit|merge|rebase|reset|tag|cherry-pick|revert|stash|switch|branch|worktree|am|apply|update-ref)\b(?!-)/, "the reviewer never writes to git history or refs; restore files with git checkout <sha> -- <paths>"],
  [/\bgit\b(\s+-C\s+\S+)*\s+checkout\s+(-b|-B|--orphan)\b/, "git checkout: the path form only (git checkout <sha> -- <paths>)"],
  [/\bgh\s+(pr\s+(review|merge|close|edit|ready|comment|reopen|create)|issue\s+(comment|edit|close|create)|release|repo\s+(edit|delete))\b/, "the reviewer reads GitHub; posting is the skill's post step"],
  [/\bgh\s+api\b(?=.*(-X|--method)\s*(POST|PATCH|PUT|DELETE))/i, "gh api: reads only"],
  [/\bgh\s+api\s+(?!graphql)\S*(?=.*\s(-f|-F|--field|--raw-field|--input)\s)/, "gh api with fields is a POST; reads only"],
  [/\bmutation\b/, "GraphQL mutations are the skill's post step"],
  [/auto-review\.mjs\s+(post|unlock|lock)\b/, "posting and the run lock belong to the orchestrating session, not a reviewer"],
];

const input = JSON.parse(fs.readFileSync(0, "utf8"));
const command = String(input.tool_input?.command ?? "");
const cwd = String(input.cwd ?? "").replace(/\\/g, "/");
const inReview = /^(\/c|c:)?\/git\/ar-(model|mx|mql)(\/|$)/i.test(cwd) || REVIEW_TREE.test(command);
const hit = inReview && DENY.find(([re]) => re.test(command));
if (hit) {
  console.log(JSON.stringify({ hookSpecificOutput: { hookEventName: "PreToolUse", permissionDecision: "deny", permissionDecisionReason: `auto-review is read-only: ${hit[1]} (${command.slice(0, 100)})` } }));
}
