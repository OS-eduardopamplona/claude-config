#!/usr/bin/env node
import { execFileSync, spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const ME = "OS-eduardopamplona";
const REPOS = {
  "OutSystems/OutSystems.Model": { clone: "C:/git/OutSystems.Model", worktree: "C:/git/ar-model" },
  "OutSystems/OutSystems.ModelExtensions": { clone: "C:/git/OutSystems.ModelExtensions", worktree: "C:/git/ar-mx" },
  "OutSystems/OutSystems.ModelQL": { clone: "C:/git/OutSystems.ModelQL", worktree: "C:/git/ar-mql" },
};
const HOME = path.join(os.homedir(), ".claude", "auto-review");
const LOCK = path.join(HOME, "lock.json");
const WEBHOOK_FILE = path.join(HOME, "slack-webhook.txt");
const ALERTED = path.join(HOME, "alerted.json");
const ALERT_QUIET_MS = 4 * 60 * 60 * 1000;
const LOCK_TTL_MS = 6 * 60 * 60 * 1000;
const MAX_PER_RUN = 3;
const LAST_ROUND = 3;
const STALE_DAYS = 7;
const SEARCH_LIMIT = 500;
const SLOTS = Number(process.env.AUTO_REVIEW_SLOTS ?? 3);
const GITVERSION = "GitVersion.yml";
const GITVERSION_DAYS = 14;
const FOOTER = "— Automated review by Claude";
const MARKER = /<!-- auto-review head=([0-9a-f]{40}) round=(\d+) -->/g;
const REPLY_MARKER = (kind) => `<!-- auto-review reply=${kind} -->`;
const SEVERITY = {
  blocker: { emoji: "🔴", label: "Blocker", blocks: true },
  major: { emoji: "🟠", label: "Major", blocks: true },
  minor: { emoji: "🟡", label: "Minor", blocks: false },
  nit: { emoji: "⚪", label: "Nit", blocks: false },
};
const LEGEND = "<sub>Severity: 🔴 Blocker · 🟠 Major (both block) · 🟡 Minor · ⚪ Nit (author decides).</sub>";
const TEST_PATH = /(^|\/)tests?\/|\.Tests?\/|Tests?\.cs$|\.test\.(m?[jt]sx?)$/i;

const run = (cmd, args, opts = {}) =>
  execFileSync(cmd, args, { encoding: "utf8", maxBuffer: 512 * 1024 * 1024, stdio: ["pipe", "pipe", "pipe"], ...opts }).replace(/\r/g, "");
const tryRun = (cmd, args, opts = {}) => {
  const r = spawnSync(cmd, args, { encoding: "utf8", maxBuffer: 512 * 1024 * 1024, ...opts });
  return { code: r.status, out: (r.stdout ?? "").replace(/\r/g, ""), err: (r.stderr ?? "").replace(/\r/g, "") };
};
const gh = (...args) => run("gh", args);
const ghJson = (...args) => JSON.parse(gh(...args));
const ghPaged = (endpoint) => JSON.parse(gh("api", "--paginate", "--slurp", endpoint)).flat();
const git = (cwd, ...args) => run("git", args, { cwd }).trim();
const short = (sha) => String(sha ?? "").slice(0, 8);
const split = (full) => {
  const [owner, name] = full.split("/");
  return { owner, name };
};

function parsePrArg(arg) {
  const m = /^([\w.-]+\/[\w.-]+)#(\d+)$/.exec(arg) ?? /github\.com\/([\w.-]+\/[\w.-]+)\/pull\/(\d+)/.exec(arg);
  if (!m || !REPOS[m[1]]) throw new Error(`not a reviewed repository's PR: ${arg}`);
  return { repo: m[1], number: Number(m[2]) };
}

function markersOf(repo, number) {
  const posts = [...ghPaged(`repos/${repo}/issues/${number}/comments`), ...ghPaged(`repos/${repo}/pulls/${number}/reviews`)];
  return posts
    .filter((p) => p.user?.login === ME)
    .flatMap((p) => [...String(p.body ?? "").matchAll(MARKER)].map((m) => ({ head: m[1], round: Number(m[2]) })))
    .sort((a, b) => a.round - b.round);
}

function fetchPr(clone, number, base) {
  git(clone, "fetch", "--quiet", "origin", base, `+refs/pull/${number}/head:refs/auto-review/pr-${number}`);
  return git(clone, "rev-parse", `refs/auto-review/pr-${number}`);
}

function hasCommit(clone, sha) {
  if (tryRun("git", ["cat-file", "-e", `${sha}^{commit}`], { cwd: clone }).code === 0) return true;
  return tryRun("git", ["fetch", "--quiet", "origin", sha], { cwd: clone }).code === 0;
}

function ownPatchId(clone, base, sha) {
  const mb = git(clone, "merge-base", `origin/${base}`, sha);
  const patch = run("git", ["diff", mb, sha], { cwd: clone });
  return run("git", ["patch-id", "--stable"], { cwd: clone, input: patch }).split(" ")[0];
}

function onlyCleanMerges(clone, base, lastHead, head) {
  if (tryRun("git", ["merge-base", "--is-ancestor", lastHead, head], { cwd: clone }).code !== 0) return false;
  const added = git(clone, "rev-list", head, `^${lastHead}`, `^origin/${base}`).split("\n").filter(Boolean);
  return added.length > 0 && added.every((sha) => {
    const [, ...parents] = git(clone, "rev-list", "--parents", "-n", "1", sha).split(" ");
    if (parents.length !== 2) return false;
    const merged = tryRun("git", ["merge-tree", "--write-tree", ...parents], { cwd: clone });
    return merged.code === 0 && merged.out.trim() === git(clone, "rev-parse", `${sha}^{tree}`);
  });
}

function searchPrs(query) {
  const since = new Date(Date.now() - STALE_DAYS * 864e5).toISOString().slice(0, 10);
  const prs = ghJson("search", "prs", "--state", "open", ...Object.keys(REPOS).flatMap((r) => ["--repo", r]), "--json", "number,repository,isDraft,author,updatedAt", "--limit", String(SEARCH_LIMIT), "--", ...`${query} draft:false updated:>=${since} -author:${ME} -author:app/dependabot -author:app/github-actions`.split(" "));
  if (prs.length >= SEARCH_LIMIT) console.error(`search "${query}" hit its limit of ${SEARCH_LIMIT}: PRs past it are not seen`);
  return prs;
}

function priority(a) {
  if (a.round > LAST_ROUND) return 4;
  return (a.requested ? 0 : 2) + (a.round > 1 ? 0 : 1);
}

function assess(repo, number, { force = false } = {}) {
  const pr = ghJson("pr", "view", String(number), "-R", repo, "--json", "number,title,url,author,isDraft,state,headRefOid,headRefName,baseRefName");
  const markers = markersOf(repo, number);
  const last = markers.at(-1) ?? null;
  const out = { repo, number, title: pr.title, url: pr.url, author: pr.author?.login, head: pr.headRefOid, base: pr.baseRefName, round: (last?.round ?? 0) + 1, lastHead: last?.head ?? null, skip: null };
  if (pr.state !== "OPEN") out.skip = `state ${pr.state}`;
  else if (pr.isDraft) out.skip = "draft";
  else if (pr.author?.login === ME) out.skip = "authored by me";
  else if (last?.head === pr.headRefOid) out.skip = `head ${short(pr.headRefOid)} already reviewed (round ${last.round})`;
  else if (last) {
    const { clone } = REPOS[repo];
    const head = fetchPr(clone, number, pr.baseRefName);
    if (hasCommit(clone, last.head) && (onlyCleanMerges(clone, pr.baseRefName, last.head, head) || ownPatchId(clone, pr.baseRefName, last.head) === ownPatchId(clone, pr.baseRefName, head)))
      out.skip = `only a clean merge of ${pr.baseRefName} since ${short(last.head)}`;
  }
  if (force && out.skip && !/^state /.test(out.skip)) out.forced = out.skip, out.skip = null;
  return out;
}

function select(args) {
  const force = args.includes("--force");
  const explicit = args.filter((a) => !a.startsWith("--")).map(parsePrArg);
  let picked = explicit;
  if (!explicit.length) {
    const key = (p) => `${p.repository.nameWithOwner}#${p.number}`;
    const requestedKeys = new Set(searchPrs("user-review-requested:@me").map(key));
    picked = searchPrs("is:pr")
      .filter((p) => !p.isDraft && p.author?.login !== ME && !p.author?.is_bot && !String(p.author?.login).startsWith("app/"))
      .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
      .map((p) => ({ repo: p.repository.nameWithOwner, number: p.number, requested: requestedKeys.has(key(p)) }));
  }
  const assessed = picked.map((p) => {
    try { return { ...assess(p.repo, p.number, { force }), requested: p.requested }; }
    catch (e) { return { repo: p.repo, number: p.number, skip: `assessment failed, retried next run: ${String(e.message).split(/\r?\n/)[0]}` }; }
  });
  const due = assessed.filter((a) => !a.skip);
  if (!explicit.length) due.sort((a, b) => priority(a) - priority(b));
  return { explicit: explicit.length > 0, due, skipped: assessed.filter((a) => a.skip).map((a) => `${a.repo}#${a.number}: ${a.skip}`) };
}

function candidates(args) {
  const { explicit, due, skipped } = select(args);
  const result = { slots: SLOTS, due: explicit ? due : due.slice(0, MAX_PER_RUN), deferred: explicit ? [] : due.slice(MAX_PER_RUN).map((a) => `${a.repo}#${a.number}`), skipped };
  console.log(JSON.stringify(result, null, 2));
}

function next(args) {
  const i = args.indexOf("--exclude");
  const excluded = new Set(i >= 0 ? fs.readFileSync(args[i + 1], "utf8").split(/\s+/).filter(Boolean) : []);
  const { due } = select([]);
  for (const a of due.filter((a) => !excluded.has(`${a.repo}#${a.number}@${a.head}`)).slice(0, MAX_PER_RUN))
    console.log(`${a.repo}#${a.number} ${a.head}`);
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
        conflicts = r.code === 1 ? r.out.split("\n").slice(1).filter(Boolean) : [];
      }
      return { number: o.number, title: o.title, draft: o.isDraft, shared: o.shared, conflicts };
    });
}

const worktreeOf = (repo, slot) => (slot > 1 ? `${REPOS[repo].worktree}-${slot}` : REPOS[repo].worktree);

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

function prepare(args) {
  if (fs.existsSync(LOCK)) fs.writeFileSync(LOCK, JSON.stringify({ ...JSON.parse(fs.readFileSync(LOCK, "utf8")), at: Date.now() }));
  const [arg, roundArg, lastHeadArg, slotArg] = args;
  const { repo, number } = parsePrArg(arg);
  const slot = Number(slotArg ?? 1);
  if (!(slot >= 1 && slot <= SLOTS)) throw new Error(`slot ${slotArg}: 1 to ${SLOTS}`);
  const { clone } = REPOS[repo];
  const worktree = worktreeOf(repo, slot);
  const pr = ghJson("pr", "view", String(number), "-R", repo, "--json", "number,title,url,body,author,headRefOid,headRefName,baseRefName,files,commits");
  const head = fetchPr(clone, number, pr.baseRefName);
  if (head !== pr.headRefOid) throw new Error(`fetched ${short(head)} but the PR's head is ${short(pr.headRefOid)}; rerun`);
  if (!fs.existsSync(path.join(worktree, ".git"))) git(clone, "worktree", "add", "--detach", worktree, head);
  else {
    restoreGitVersion(worktree);
    git(worktree, "checkout", "--quiet", "--force", "--detach", head);
    git(worktree, "clean", "-fdqx", "-e", "bin/", "-e", "obj/", "-e", "node_modules/");
  }
  shortenGitVersion(worktree);
  const mergeBase = git(clone, "merge-base", `origin/${pr.baseRefName}`, head);
  const round = Number(roundArg ?? 1);
  const lastHead = lastHeadArg && lastHeadArg !== "-" ? lastHeadArg : null;
  const dir = path.join(HOME, "runs", `${split(repo).name}-${number}-${short(head)}-r${round}`);
  fs.mkdirSync(dir, { recursive: true });
  const files = pr.files.map((f) => f.path);
  const diff = run("git", ["diff", mergeBase, head], { cwd: clone });
  fs.writeFileSync(path.join(dir, "diff.patch"), diff);
  let deltaFiles = [];
  if (lastHead && hasCommit(clone, lastHead)) {
    const lastFiles = git(clone, "diff", "--name-only", git(clone, "merge-base", `origin/${pr.baseRefName}`, lastHead), lastHead).split("\n").filter(Boolean);
    const scope = [...new Set([...files, ...lastFiles])];
    fs.writeFileSync(path.join(dir, "delta.patch"), run("git", ["diff", lastHead, head, "--", ...scope], { cwd: clone }));
    deltaFiles = git(clone, "diff", "--name-only", lastHead, head, "--", ...scope).split("\n").filter(Boolean);
  }
  const merges = git(clone, "rev-list", "--merges", `${mergeBase}..${head}`).split("\n").filter(Boolean);
  const checks = tryRun("gh", ["pr", "checks", String(number), "-R", repo]);
  fs.writeFileSync(path.join(dir, "checks.txt"), checks.out + checks.err);
  fs.writeFileSync(path.join(dir, "threads.json"), JSON.stringify(threadsOf(repo, number), null, 2));
  const conversation = [
    ...ghPaged(`repos/${repo}/issues/${number}/comments`).map((c) => ({ kind: "comment", id: c.id, author: c.user?.login, at: c.created_at, body: c.body })),
    ...ghPaged(`repos/${repo}/pulls/${number}/reviews`).filter((r) => r.body).map((r) => ({ kind: "review", id: r.id, author: r.user?.login, at: r.submitted_at, state: r.state, body: r.body })),
  ].sort((a, b) => String(a.at).localeCompare(String(b.at)));
  fs.writeFileSync(path.join(dir, "conversation.json"), JSON.stringify(conversation, null, 2));
  fs.writeFileSync(path.join(dir, "overlaps.json"), JSON.stringify(overlaps(repo, clone, number, head, files), null, 2));
  const meta = {
    repo, number, title: pr.title, url: pr.url, author: pr.author?.login, body: pr.body, base: pr.baseRefName, head, mergeBase,
    round, lastRound: round >= LAST_ROUND, lastHead, worktree, files,
    testFiles: files.filter((f) => TEST_PATH.test(f)), productFiles: files.filter((f) => !TEST_PATH.test(f)),
    deltaFiles, merges, commits: pr.commits.map((c) => `${short(c.oid)} ${c.messageHeadline}`),
  };
  fs.writeFileSync(path.join(dir, "pr.json"), JSON.stringify(meta, null, 2));
  console.log(dir);
}

function anchorable(diff) {
  const lines = new Map();
  let file = null;
  let n = 0;
  for (const l of diff.split("\n")) {
    if (l.startsWith("+++ ")) {
      file = l === "+++ /dev/null" ? null : l.slice(6);
      if (file) lines.set(file, new Set());
    } else if (l.startsWith("@@")) n = Number(/\+(\d+)/.exec(l)[1]);
    else if (file && !l.startsWith("--- ") && !l.startsWith("diff ") && !l.startsWith("index ")) {
      if (l.startsWith("+") || l.startsWith(" ")) lines.get(file).add(n++);
    }
  }
  return lines;
}

const where = (f) => `\`${f.file}${f.line ? `:${f.line}` : ""}\``;
const renderFinding = (f) => {
  const s = SEVERITY[f.severity];
  return [`${s.emoji} **${s.label}** · ${f.category} · ${f.confidence}`, "", f.defect, "", `- **Scenario:** ${f.scenario}`, `- **Fix:** ${f.fix}`, "", FOOTER].join("\n");
};
const bullets = (v) => (Array.isArray(v) ? v : [v ?? ""]).map((x) => String(x).trim()).filter(Boolean).map((x) => `- ${x}`);
const listItem = (f) => `- ${SEVERITY[f.severity].emoji} ${where(f)}: ${f.defect}`;

function validateVerdict(v) {
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
  if (errors.length) throw new Error(`verified.json is malformed:\n${errors.join("\n")}`);
}

function plan(dir) {
  const meta = JSON.parse(fs.readFileSync(path.join(dir, "pr.json"), "utf8"));
  const v = JSON.parse(fs.readFileSync(path.join(dir, "verified.json"), "utf8"));
  validateVerdict(v);
  const threads = JSON.parse(fs.readFileSync(path.join(dir, "threads.json"), "utf8"));
  const anchors = anchorable(fs.readFileSync(path.join(dir, "diff.patch"), "utf8"));
  const deltaAnchors = meta.lastHead && fs.existsSync(path.join(dir, "delta.patch")) ? anchorable(fs.readFileSync(path.join(dir, "delta.patch"), "utf8")) : anchors;
  const ownComments = threads.filter((t) => t.own);
  const dropped = [];
  const left = [];
  let findings = v.findings ?? [];
  if (meta.lastRound) {
    findings = findings.filter((f) => {
      const onChanged = f.line && deltaAnchors.get(f.file)?.has(f.line);
      if (!SEVERITY[f.severity].blocks) return dropped.push({ f, why: `last round: ${f.severity} not posted` }), false;
      if (!onChanged) return dropped.push({ f, why: "last round: not on a line this round changed" }), false;
      if (f.confidence === "PLAUSIBLE") return left.push(f), false;
      return true;
    });
  }
  findings = findings.filter((f) => {
    if (SEVERITY[f.severity].blocks) return true;
    const again = ownComments.find((t) => t.path === f.file && f.line && Math.abs((t.line ?? -99) - f.line) <= 3);
    return again ? (dropped.push({ f, why: `already raised in thread ${again.id}` }), false) : true;
  });
  const inline = findings.filter((f) => f.line && anchors.get(f.file)?.has(f.line));
  const unanchored = findings.filter((f) => !inline.includes(f));
  const blocking = findings.filter((f) => SEVERITY[f.severity].blocks);
  const count = (sev) => findings.filter((f) => f.severity === sev).length;
  const tally = Object.keys(SEVERITY).filter(count).map((s) => `${count(s)} ${SEVERITY[s].label}`).join(", ");

  const replies = [];
  for (const r of v.replies ?? []) {
    const t = threads.find((x) => x.id === r.thread_id);
    if (!t) { dropped.push({ r, why: "no such thread" }); continue; }
    if (!t.own) { dropped.push({ r, why: "not one of my threads" }); continue; }
    if (r.kind === "rejected" && t.comments.some((c) => c.author === ME && c.body.includes(REPLY_MARKER("rejected")))) { dropped.push({ r, why: "already argued once in this thread" }); continue; }
    if (r.kind === "fixed" && t.resolved) { dropped.push({ r, why: "thread already resolved" }); continue; }
    const text = {
      fixed: `Fixed at ${short(meta.head)}.${r.body ? ` ${r.body}` : ""}`,
      still_open: `Still open at ${short(meta.head)}: ${r.body}`,
      accepted: r.body,
      rejected: r.body,
      correction: r.body,
    }[r.kind];
    replies.push({ thread: t.id, comment: t.comments[0].id, resolve: ["fixed", "accepted"].includes(r.kind), body: `${text}\n\n${FOOTER}\n${REPLY_MARKER(r.kind)}` });
  }
  const resolved = replies.filter((r) => r.resolve).map((r) => threads.find((t) => t.id === r.thread));

  const marker = `<!-- auto-review head=${meta.head} round=${meta.round} -->`;
  const headline = blocking.length
    ? `**${findings.length} finding${findings.length > 1 ? "s" : ""}: ${tally}**${inline.length ? ", inline" : ""}.`
    : `**No blocking issues**${findings.length ? ` (${tally}, the author decides)` : ""}.`;
  const notes = bullets(v.notes);
  const body = [
    `🤖 **Automated review by Claude** · round ${meta.round} · \`${short(meta.head)}\``,
    "",
    headline,
    ...(unanchored.length ? ["", "**Not anchorable inline**", ...unanchored.flatMap((f) => [listItem(f), `  - **Scenario:** ${f.scenario}`, `  - **Fix:** ${f.fix}`])] : []),
    ...(left.length ? ["", "**Left to the human reviewer** (plausible, unverified, not blocking in this last round)", ...left.map(listItem)] : []),
    ...(resolved.length ? ["", "**Resolved since the last round**", ...resolved.map((t) => `- \`${t.path}${t.line ? `:${t.line}` : ""}\``)] : []),
    ...(notes.length ? ["", "**Notes**", ...notes] : []),
    ...(findings.length ? ["", LEGEND] : []),
    ...(blocking.length ? [] : ["", `@${ME} for the human pass.`]),
    "",
    marker,
  ].join("\n");
  const kind = inline.length ? "review" : "comment";
  return { meta, kind, body, ready: !blocking.length, tally, inline: inline.map((f) => ({ path: f.file, line: f.line, side: "RIGHT", body: renderFinding(f) })), replies, dropped };
}

function renderPlan(p) {
  const out = [`# ${p.meta.repo}#${p.meta.number} round ${p.meta.round} at ${short(p.meta.head)}: ${p.kind === "review" ? "COMMENTED review" : "issue comment"}`, "", "## Body", "", p.body];
  for (const c of p.inline) out.push("", `## Inline ${c.path}:${c.line}`, "", c.body);
  for (const r of p.replies) out.push("", `## Reply to comment ${r.comment}${r.resolve ? " (then resolve)" : ""}`, "", r.body);
  if (p.dropped.length) out.push("", "## Not posted", "", ...p.dropped.map((d) => `- ${d.why}: ${d.f ? `${where(d.f)} ${d.f.defect}` : `${d.r.kind} on ${d.r.thread_id}`}`));
  return out.join("\n");
}

async function post(args) {
  const dir = args.find((a) => !a.startsWith("--"));
  const dry = args.includes("--dry-run") || process.env.AUTO_REVIEW_DRY_RUN === "1";
  const p = plan(dir);
  const rendered = renderPlan(p);
  fs.writeFileSync(path.join(dir, "post.md"), rendered);
  if (dry) {
    console.log(rendered);
    console.log(`\n(dry run: nothing posted; ${path.join(dir, "post.md")})`);
    return;
  }
  const { repo, number, head } = p.meta;
  if (assess(repo, number).skip?.includes("already reviewed")) throw new Error(`head ${short(head)} already carries a marker; not posting twice`);
  for (const r of p.replies) {
    const payload = path.join(dir, `reply-${r.comment}.json`);
    fs.writeFileSync(payload, JSON.stringify({ body: r.body }));
    gh("api", "--method", "POST", `repos/${repo}/pulls/${number}/comments/${r.comment}/replies`, "--input", payload);
    if (r.resolve) gh("api", "graphql", "-f", "query=mutation($id:ID!){resolveReviewThread(input:{threadId:$id}){thread{isResolved}}}", "-F", `id=${r.thread}`);
  }
  if (p.kind === "review") {
    const payload = path.join(dir, "review.json");
    fs.writeFileSync(payload, JSON.stringify({ commit_id: head, event: "COMMENT", body: p.body, comments: p.inline }));
    const res = JSON.parse(gh("api", "--method", "POST", `repos/${repo}/pulls/${number}/reviews`, "--input", payload));
    console.log(res.html_url);
  } else {
    const payload = path.join(dir, "comment.json");
    fs.writeFileSync(payload, JSON.stringify({ body: p.body }));
    const res = JSON.parse(gh("api", "--method", "POST", `repos/${repo}/issues/${number}/comments`, "--input", payload));
    console.log(res.html_url);
  }
  if (p.ready) await notifyReady(p);
}

async function notifyReady(p) {
  const { repo, number, round, title, url } = p.meta;
  const summary = `Round ${round}: no blocking issues${p.tally ? ` (${p.tally}, the author decides)` : ""}.`;
  await slack({ repo, pr: String(number), title: title ?? "", url: url ?? `https://github.com/${repo}/pull/${number}`, summary });
}

async function checkRun([log]) {
  const results = fs.readFileSync(log, "utf8").split(/\r?\n/).flatMap((l) => { try { const o = JSON.parse(l); return o.type === "result" ? [o] : []; } catch { return []; } });
  const result = results.at(-1);
  if (result && !result.is_error) return;
  process.exitCode = 4;
  const text = String(result?.result ?? `the review run ended with no result (${log})`).split(/\r?\n/)[0];
  console.log(`review run failed: ${text}`);
  const last = fs.existsSync(ALERTED) ? JSON.parse(fs.readFileSync(ALERTED, "utf8")) : null;
  if (last?.text === text && Date.now() - last.at < ALERT_QUIET_MS) return console.log(`already alerted at ${new Date(last.at).toISOString()}: ${text}`);
  fs.writeFileSync(ALERTED, JSON.stringify({ at: Date.now(), text }));
  await slack({ repo: "auto-review", pr: "-", title: "Auto-review stopped: a review run failed", url: "https://github.com/pulls/review-requested", summary: text });
}

async function slack(fields) {
  if (!fs.existsSync(WEBHOOK_FILE)) return console.log(`no ${WEBHOOK_FILE}: Slack not notified`);
  try {
    const res = await fetch(fs.readFileSync(WEBHOOK_FILE, "utf8").trim(), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(fields),
    });
    console.log(res.ok ? "Slack notified" : `Slack webhook answered ${res.status}: ${await res.text()}`);
  } catch (e) {
    console.log(`Slack webhook failed: ${e.message}`);
  }
}

function lock(args = []) {
  if (process.env.AUTO_REVIEW_LOCKED) return console.log("run.sh holds the lock");
  fs.mkdirSync(HOME, { recursive: true });
  if (fs.existsSync(LOCK) && !args.includes("--renew")) {
    const held = JSON.parse(fs.readFileSync(LOCK, "utf8"));
    if (Date.now() - held.at < LOCK_TTL_MS) {
      console.error(`another run holds the lock since ${new Date(held.at).toISOString()}`);
      process.exit(3);
    }
  }
  fs.writeFileSync(LOCK, JSON.stringify({ at: Date.now(), pid: process.ppid }));
}

const [verb, ...rest] = process.argv.slice(2);
const verbs = { lock, unlock: () => process.env.AUTO_REVIEW_LOCKED || fs.rmSync(LOCK, { force: true }), candidates, next, prepare, post, plan: (a) => console.log(renderPlan(plan(a[0]))), notify: (a) => notifyReady(plan(a[0])), "check-run": checkRun };
if (!verbs[verb]) {
  console.error("usage: auto-review.mjs lock [--renew] | unlock | next [--exclude <file>] | candidates [--force] [<owner/repo>#<n>...] | prepare <owner/repo>#<n> <round> <lastHead|-> [<slot>] | post <run dir> [--dry-run] | notify <run dir> | check-run <log>");
  process.exit(2);
}
try {
  await verbs[verb](rest);
} catch (e) {
  console.error(e.stderr ? `${e.message}\n${e.stderr}` : e.message);
  process.exit(1);
}
