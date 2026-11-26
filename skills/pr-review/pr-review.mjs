#!/usr/bin/env node
import { execFileSync, spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const ME = "OS-eduardopamplona";
export const REPOS = {
  "OutSystems/OutSystems.Model": { clone: "C:/git/OutSystems.Model", worktree: "C:/git/ar-model" },
  "OutSystems/OutSystems.ModelExtensions": { clone: "C:/git/OutSystems.ModelExtensions", worktree: "C:/git/ar-mx" },
  "OutSystems/OutSystems.ModelQL": { clone: "C:/git/OutSystems.ModelQL", worktree: "C:/git/ar-mql" },
};
export const RUNS = path.join(os.homedir(), ".claude", "pr-review", "runs");
export const FOOTER = "— Automated review by Claude";
export const SEVERITY = {
  blocker: { emoji: "🔴", label: "Blocker", blocks: true },
  major: { emoji: "🟠", label: "Major", blocks: true },
  minor: { emoji: "🟡", label: "Minor", blocks: false },
  nit: { emoji: "⚪", label: "Nit", blocks: false },
};
const GITVERSION = "GitVersion.yml";
const GITVERSION_DAYS = 14;
const TEST_PATH = /(^|\/)tests?\/|\.Tests?\/|Tests?\.cs$|\.test\.(m?[jt]sx?)$/i;

export const run = (cmd, args, opts = {}) =>
  execFileSync(cmd, args, { encoding: "utf8", maxBuffer: 512 * 1024 * 1024, stdio: ["pipe", "pipe", "pipe"], ...opts }).replace(/\r/g, "");
export const tryRun = (cmd, args, opts = {}) => {
  const r = spawnSync(cmd, args, { encoding: "utf8", maxBuffer: 512 * 1024 * 1024, ...opts });
  return { code: r.status, out: (r.stdout ?? "").replace(/\r/g, ""), err: (r.stderr ?? "").replace(/\r/g, "") };
};
export const gh = (...args) => run("gh", args);
export const ghJson = (...args) => JSON.parse(gh(...args));
export const ghPaged = (endpoint) => JSON.parse(gh("api", "--paginate", "--slurp", endpoint)).flat();
export const git = (cwd, ...args) => run("git", args, { cwd }).trim();
export const short = (sha) => String(sha ?? "").slice(0, 8);
const lines = (text) => text.split("\n").filter(Boolean);
const samePath = (a, b) => path.resolve(a).replace(/\\/g, "/").toLowerCase() === path.resolve(b).replace(/\\/g, "/").toLowerCase();
const split = (full) => {
  const [owner, name] = full.split("/");
  return { owner, name };
};

export function parsePrArg(arg) {
  const m = /^([\w.-]+\/[\w.-]+)#(\d+)$/.exec(arg) ?? /github\.com\/([\w.-]+\/[\w.-]+)\/pull\/(\d+)/.exec(arg);
  if (!m || !REPOS[m[1]]) throw new Error(`not a reviewed repository's PR: ${arg}`);
  return { repo: m[1], number: Number(m[2]) };
}

function fetchPr(clone, number, base) {
  git(clone, "fetch", "--quiet", "origin", base, `+refs/pull/${number}/head:refs/auto-review/pr-${number}`);
  return git(clone, "rev-parse", `refs/auto-review/pr-${number}`);
}

function hasCommit(clone, sha) {
  if (tryRun("git", ["cat-file", "-e", `${sha}^{commit}`], { cwd: clone }).code === 0) return true;
  return tryRun("git", ["fetch", "--quiet", "origin", sha], { cwd: clone }).code === 0;
}

function threadsOf(repo, number) {
  const { owner, name } = split(repo);
  const query = `query($o:String!,$r:String!,$n:Int!,$endCursor:String){repository(owner:$o,name:$r){pullRequest(number:$n){reviewThreads(first:50,after:$endCursor){pageInfo{hasNextPage endCursor} nodes{id isResolved isOutdated path line originalLine comments(first:50){nodes{databaseId author{login} body createdAt}}}}}}}`;
  const pages = JSON.parse(gh("api", "graphql", "--paginate", "--slurp", "-f", `query=${query}`, "-F", `o=${owner}`, "-F", `r=${name}`, "-F", `n=${number}`));
  return pages.flatMap((p) => p.data.repository.pullRequest.reviewThreads.nodes).map((t) => ({
    id: t.id, resolved: t.isResolved, outdated: t.isOutdated, path: t.path, line: t.line ?? t.originalLine,
    own: t.comments.nodes[0]?.author?.login === ME && t.comments.nodes[0]?.body.includes(FOOTER),
    comments: t.comments.nodes.map((c) => ({ id: c.databaseId, author: c.author?.login, at: c.createdAt, body: c.body })),
  }));
}

function overlaps(repo, clone, number, head, files) {
  const mine = new Set(files);
  const open = ghJson("pr", "list", "-R", repo, "--state", "open", "--limit", "100", "--json", "number,title,headRefOid,files,isDraft");
  return open
    .filter((o) => o.number !== number)
    .map((o) => ({ ...o, shared: (o.files ?? []).map((f) => f.path).filter((f) => mine.has(f)) }))
    .filter((o) => o.shared.length)
    .map((o) => {
      let conflicts = null;
      if (tryRun("git", ["fetch", "--quiet", "origin", `+refs/pull/${o.number}/head:refs/auto-review/pr-${o.number}`], { cwd: clone }).code === 0) {
        const r = tryRun("git", ["merge-tree", "--write-tree", "--name-only", "--no-messages", head, `refs/auto-review/pr-${o.number}`], { cwd: clone });
        conflicts = r.code === 1 ? lines(r.out).slice(1) : [];
      }
      return { number: o.number, title: o.title, draft: o.isDraft, shared: o.shared, conflicts };
    });
}

function diffPaths(clone, args, paths) {
  const batches = [[]];
  let length = 0;
  for (const p of paths) {
    if (length + p.length > 16000) batches.push([]), (length = 0);
    batches.at(-1).push(p);
    length += p.length + 3;
  }
  return batches.filter((b) => b.length).map((b) => run("git", ["diff", ...args, "--", ...b], { cwd: clone })).join("");
}

function restoreGitVersion(worktree) {
  if (!fs.existsSync(path.join(worktree, GITVERSION))) return;
  tryRun("git", ["update-index", "--no-skip-worktree", GITVERSION], { cwd: worktree });
  tryRun("git", ["checkout", "--", GITVERSION], { cwd: worktree });
}

function shortenGitVersion(worktree) {
  const file = path.join(worktree, GITVERSION);
  if (!fs.existsSync(file)) return;
  const since = new Date(Date.now() - GITVERSION_DAYS * 864e5).toISOString().slice(0, 10);
  const text = fs.readFileSync(file, "utf8");
  const shortened = text.replace(/^(\s*commits-before:\s*)\d{4}-\d{2}-\d{2}/m, `$1${since}`);
  if (shortened === text) return;
  fs.writeFileSync(file, shortened);
  git(worktree, "update-index", "--skip-worktree", GITVERSION);
}

function checkOut(clone, worktree, head, deep) {
  if (!fs.existsSync(path.join(worktree, ".git"))) git(clone, "worktree", "add", "--detach", worktree, head);
  else {
    restoreGitVersion(worktree);
    git(worktree, "checkout", "--quiet", "--force", "--detach", head);
    git(worktree, "clean", "-fdqx");
  }
  if (deep) shortenGitVersion(worktree);
}

function writeRun(dir, files) {
  fs.mkdirSync(dir, { recursive: true });
  for (const f of ["verdict.json", "verified.json"]) fs.rmSync(path.join(dir, f), { force: true });
  for (const [name, content] of Object.entries(files))
    fs.writeFileSync(path.join(dir, name), typeof content === "string" ? content : JSON.stringify(content, null, 2));
}

function baseDrift(clone, mergeBase, head, baseTip, files) {
  const merged = tryRun("git", ["merge-tree", "--write-tree", "--name-only", "--no-messages", head, baseTip], { cwd: clone });
  return { patch: diffPaths(clone, [mergeBase, baseTip], files), conflicts: merged.code === 1 ? lines(merged.out).slice(1) : [] };
}

function changedFiles(clone, mergeBase, head) {
  const files = lines(git(clone, "diff", "--name-only", mergeBase, head));
  return { files, testFiles: files.filter((f) => TEST_PATH.test(f)), productFiles: files.filter((f) => !TEST_PATH.test(f)) };
}

function preparePr(arg, round, lastHead, { deep, slot }) {
  const { repo, number } = parsePrArg(arg);
  const { clone } = REPOS[repo];
  const worktree = REPOS[repo].worktree + slot;
  const pr = ghJson("pr", "view", String(number), "-R", repo, "--json", "number,title,url,body,author,headRefOid,headRefName,baseRefName,commits");
  const head = fetchPr(clone, number, pr.baseRefName);
  if (head !== pr.headRefOid) throw new Error(`fetched ${short(head)} but the PR's head is ${short(pr.headRefOid)}; rerun`);
  checkOut(clone, worktree, head, deep);
  const mergeBase = git(clone, "merge-base", `origin/${pr.baseRefName}`, head);
  const changed = changedFiles(clone, mergeBase, head);
  const extra = {};
  let deltaFiles = [];
  if (lastHead && hasCommit(clone, lastHead)) {
    const lastFiles = lines(git(clone, "diff", "--name-only", git(clone, "merge-base", `origin/${pr.baseRefName}`, lastHead), lastHead));
    const scope = [...new Set([...changed.files, ...lastFiles])];
    extra["delta.patch"] = diffPaths(clone, [lastHead, head], scope);
    deltaFiles = lines(diffPaths(clone, ["--name-only", lastHead, head], scope));
  }
  const drift = baseDrift(clone, mergeBase, head, git(clone, "rev-parse", `origin/${pr.baseRefName}`), changed.files);
  const checks = tryRun("gh", ["pr", "checks", String(number), "-R", repo]);
  const conversation = [
    ...ghPaged(`repos/${repo}/issues/${number}/comments`).map((c) => ({ kind: "comment", id: c.id, author: c.user?.login, at: c.created_at, body: c.body })),
    ...ghPaged(`repos/${repo}/pulls/${number}/reviews`).filter((r) => r.body).map((r) => ({ kind: "review", id: r.id, author: r.user?.login, at: r.submitted_at, state: r.state, body: r.body })),
  ].sort((a, b) => String(a.at).localeCompare(String(b.at)));
  const dir = path.join(RUNS, `${split(repo).name}-${number}-${short(head)}-r${round}`);
  writeRun(dir, {
    ...extra,
    "diff.patch": run("git", ["diff", mergeBase, head], { cwd: clone }),
    "base.patch": drift.patch,
    "checks.txt": checks.out + checks.err,
    "threads.json": threadsOf(repo, number),
    "conversation.json": conversation,
    "overlaps.json": overlaps(repo, clone, number, head, changed.files),
    "pr.json": {
      repo, number, local: false, title: pr.title, url: pr.url, author: pr.author?.login, body: pr.body, base: pr.baseRefName, head, mergeBase,
      round, lastHead, worktree, deep, ...changed, deltaFiles, baseConflicts: drift.conflicts,
      merges: lines(git(clone, "rev-list", "--merges", `${mergeBase}..${head}`)),
      commits: pr.commits.map((c) => `${short(c.oid)} ${c.messageHeadline}`),
    },
  });
  return dir;
}

function prepareLocal(where, { deep, slot, base }) {
  const top = git(where, "rev-parse", "--show-toplevel");
  const common = path.resolve(top, git(top, "rev-parse", "--git-common-dir"));
  const repo = Object.keys(REPOS).find((r) => samePath(path.join(REPOS[r].clone, ".git"), common));
  if (!repo) throw new Error(`${top} is not ${Object.values(REPOS).map((r) => r.clone).join(", ")} or one of its worktrees`);
  const { clone } = REPOS[repo];
  const worktree = REPOS[repo].worktree + slot;
  const baseBranch = base ?? git(clone, "rev-parse", "--abbrev-ref", "origin/HEAD").replace(/^origin\//, "");
  git(clone, "fetch", "--quiet", "origin", baseBranch);
  const branch = git(top, "rev-parse", "--abbrev-ref", "HEAD");
  const tip = git(top, "rev-parse", "HEAD");
  const head = git(top, "stash", "create") || tip;
  checkOut(clone, worktree, head, deep);
  const mergeBase = git(clone, "merge-base", `origin/${baseBranch}`, tip);
  const changed = changedFiles(clone, mergeBase, head);
  const drift = baseDrift(clone, mergeBase, head, git(clone, "rev-parse", `origin/${baseBranch}`), changed.files);
  const dir = path.join(RUNS, `${split(repo).name}-local-${branch.replace(/[^\w.-]+/g, "-")}-${short(head)}`);
  writeRun(dir, {
    "diff.patch": run("git", ["diff", mergeBase, head], { cwd: clone }),
    "base.patch": drift.patch,
    "checks.txt": "No CI: a local branch, not a pull request.\n",
    "threads.json": [],
    "conversation.json": [],
    "overlaps.json": overlaps(repo, clone, null, head, changed.files),
    "pr.json": {
      repo, number: null, local: true, source: top, title: branch, url: null, author: null, body: "", base: baseBranch, head, mergeBase,
      uncommitted: head !== tip, round: 1, lastHead: null, worktree, deep, ...changed, deltaFiles: [], baseConflicts: drift.conflicts,
      merges: lines(git(clone, "rev-list", "--merges", `${mergeBase}..${tip}`)),
      commits: lines(git(clone, "log", "--format=%h %s", `${mergeBase}..${tip}`)),
    },
  });
  return dir;
}

function prepare(args) {
  const flag = (name) => {
    const i = args.indexOf(name);
    return i < 0 ? undefined : args[i + 1];
  };
  const deep = args.includes("--deep");
  const slot = args.includes("--chat") ? "-chat" : "";
  const local = args.includes("--local") ? (flag("--local")?.startsWith("--") ? "." : flag("--local") ?? ".") : undefined;
  const rest = args.filter((a, i) => !a.startsWith("--") && !["--local", "--base"].includes(args[i - 1]));
  if (local !== undefined) return console.log(prepareLocal(local, { deep, slot, base: flag("--base") }));
  const [arg, roundArg, lastHeadArg] = rest;
  console.log(preparePr(arg, Number(roundArg ?? 1), lastHeadArg && lastHeadArg !== "-" ? lastHeadArg : null, { deep, slot }));
}

export function validateVerdict(v, name = "verified.json") {
  const errors = [];
  for (const [i, f] of (v.findings ?? []).entries()) {
    if (!SEVERITY[f.severity]) errors.push(`finding ${i}: severity ${f.severity}`);
    if (!["CONFIRMED", "PLAUSIBLE"].includes(f.confidence)) errors.push(`finding ${i}: confidence ${f.confidence}`);
    for (const k of ["file", "category", "defect", "scenario", "fix"]) if (!f[k]) errors.push(`finding ${i}: no ${k}`);
  }
  for (const [i, r] of (v.replies ?? []).entries()) {
    if (!["fixed", "still_open", "accepted", "rejected", "correction"].includes(r.kind)) errors.push(`reply ${i}: kind ${r.kind}`);
    if (!r.thread_id) errors.push(`reply ${i}: no thread_id`);
  }
  if (errors.length) throw new Error(`${name} is malformed:\n${errors.join("\n")}`);
}

function validate([file]) {
  validateVerdict(JSON.parse(fs.readFileSync(file, "utf8")), path.basename(file));
  console.log(`${file}: valid`);
}

function needsVerify([dir]) {
  const v = JSON.parse(fs.readFileSync(path.join(dir, "verdict.json"), "utf8"));
  const verify = (v.replies ?? []).some((r) => r.rebuttal) || (v.findings ?? []).some((f) => SEVERITY[f.severity]?.blocks);
  console.log(verify ? "verify" : "skip");
}

const isMain = process.argv[1] && samePath(process.argv[1], fileURLToPath(import.meta.url));
if (isMain) {
  const [verb, ...rest] = process.argv.slice(2);
  const verbs = { prepare, validate, "needs-verify": needsVerify };
  if (!verbs[verb]) {
    console.error("usage: pr-review.mjs prepare <PR> [<round> <lastHead|->] [--deep] [--chat] | prepare --local <path> [--base <branch>] [--deep] [--chat] | validate <verdict file> | needs-verify <run dir>");
    process.exit(2);
  }
  try {
    await verbs[verb](rest);
  } catch (e) {
    console.error(e.stderr ? `${e.message}\n${e.stderr}` : e.message);
    process.exit(1);
  }
}
