#!/usr/bin/env node
import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { ME, REPOS, FOOTER, SEVERITY, gh, ghJson, ghPaged, short, parsePrArg, validateVerdict } from "../pr-review/pr-review.mjs";

const HOME = path.join(os.homedir(), ".claude", "auto-review");
const LOCK = path.join(HOME, "lock.json");
const QUEUE = path.join(HOME, "requested.txt");
const WEBHOOK_FILE = path.join(HOME, "slack-webhook.txt");
const ALERTED = path.join(HOME, "alerted.json");
const LOCK_TTL_MS = 3 * 60 * 60 * 1000;
const ALERT_QUIET_MS = 4 * 60 * 60 * 1000;
const OPTIONS = new Set(["dry-run", "deep"]);
const MAX_PER_RUN = 4;
const STALE_DAYS = 7;
const SEARCH_LIMIT = 500;
const MARKER = /<!-- auto-review head=([0-9a-f]{40}) round=(\d+)(?: requested=(\S+))? -->/g;
const REPLY_MARKER = (kind) => `<!-- auto-review reply=${kind} -->`;
const LEGEND = "<sub>Severity: 🔴 Blocker · 🟠 Major (both block) · 🟡 Minor · ⚪ Nit (author decides).</sub>";
const RE_REQUEST = "Once you've addressed these, or replied in a thread where you disagree, re-request my review.";

const readJson = (file) => (fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, "utf8")) : null);

function markersOf(repo, number) {
  const posts = [
    ...ghPaged(`repos/${repo}/issues/${number}/comments`).map((c) => ({ ...c, at: c.created_at })),
    ...ghPaged(`repos/${repo}/pulls/${number}/reviews`).map((r) => ({ ...r, at: r.submitted_at })),
  ];
  return posts
    .filter((p) => p.user?.login === ME)
    .flatMap((p) => [...String(p.body ?? "").matchAll(MARKER)].map((m) => ({ head: m[1], round: Number(m[2]), answered: m[3] ?? p.at })))
    .sort((a, b) => a.round - b.round);
}

function lastRequestOf(repo, number) {
  return ghPaged(`repos/${repo}/issues/${number}/timeline?per_page=100`)
    .filter((e) => e.event === "review_requested" && e.requested_reviewer?.login === ME)
    .map((e) => e.created_at)
    .sort()
    .at(-1) ?? null;
}

function searchRequested() {
  const since = new Date(Date.now() - STALE_DAYS * 864e5).toISOString().slice(0, 10);
  const prs = ghJson("search", "prs", "--state", "open", ...Object.keys(REPOS).flatMap((r) => ["--repo", r]), "--json", "number,repository,isDraft,author,updatedAt", "--limit", String(SEARCH_LIMIT), "--", "user-review-requested:@me", "draft:false", `updated:>=${since}`, `-author:${ME}`, "-author:app/dependabot", "-author:app/github-actions");
  if (prs.length >= SEARCH_LIMIT) console.error(`search hit its limit of ${SEARCH_LIMIT}: PRs past it are not seen`);
  return prs.filter((p) => !p.isDraft && !p.author?.is_bot && !String(p.author?.login).startsWith("app/"));
}

function assess(repo, number, { force = false } = {}) {
  const pr = ghJson("pr", "view", String(number), "-R", repo, "--json", "state,isDraft,author");
  const last = markersOf(repo, number).at(-1) ?? null;
  const requested = lastRequestOf(repo, number);
  const out = { repo, number, round: (last?.round ?? 0) + 1, lastHead: last?.head ?? null, requested, skip: null };
  if (pr.state !== "OPEN") out.skip = `state ${pr.state}`;
  else if (pr.isDraft) out.skip = "draft";
  else if (pr.author?.login === ME) out.skip = "authored by me";
  else if (last && !(requested && requested > last.answered)) out.skip = `no re-request since round ${last.round}`;
  if (force && out.skip && !/^state /.test(out.skip)) out.forced = out.skip, out.skip = null;
  return out;
}

function select(args) {
  const force = args.includes("--force");
  const explicit = args.filter((a) => !a.startsWith("--")).map(parsePrArg);
  const picked = explicit.length
    ? explicit
    : searchRequested().sort((a, b) => b.updatedAt.localeCompare(a.updatedAt)).map((p) => ({ repo: p.repository.nameWithOwner, number: p.number }));
  const assessed = picked.map((p) => {
    try { return assess(p.repo, p.number, { force }); }
    catch (e) { return { ...p, skip: `assessment failed, retried next run: ${String(e.message).split(/\r?\n/)[0]}` }; }
  });
  const due = assessed.filter((a) => !a.skip);
  if (!explicit.length) due.sort((a, b) => (a.round > 1 ? 0 : 1) - (b.round > 1 ? 0 : 1));
  return { explicit: explicit.length > 0, due, skipped: assessed.filter((a) => a.skip).map((a) => `${a.repo}#${a.number}: ${a.skip}`) };
}

function candidates(args) {
  const { due, skipped } = select(args);
  console.log(JSON.stringify({ due: due.map((a) => `${a.repo}#${a.number} round ${a.round}${a.forced ? ` (forced: ${a.forced})` : ""}`), skipped }, null, 2));
}

function next(args) {
  const options = args.filter((a) => OPTIONS.has(a));
  const { explicit, due, skipped } = select(args.filter((a) => !OPTIONS.has(a)));
  for (const s of explicit ? skipped : []) console.error(`skipped ${s}`);
  for (const a of explicit ? due : due.slice(0, MAX_PER_RUN)) console.log([`${a.repo}#${a.number}`, a.round, a.lastHead ?? "-", a.requested ?? "-", ...options].join(" "));
}

function queue(args) {
  const prs = args.filter((a) => !OPTIONS.has(a));
  if (!prs.length) throw new Error("queue: no PRs");
  prs.forEach(parsePrArg);
  const options = args.filter((a) => OPTIONS.has(a));
  fs.mkdirSync(HOME, { recursive: true });
  fs.appendFileSync(QUEUE, prs.map((pr) => [...options, pr].join(" ") + "\n").join(""));
  for (const pr of prs) console.log(`${pr}: queued behind the run in progress`);
}

function take() {
  const taking = `${QUEUE}.${process.pid}`;
  try {
    fs.renameSync(QUEUE, taking);
  } catch (e) {
    if (e.code === "ENOENT") return;
    throw e;
  }
  const lines = fs.readFileSync(taking, "utf8").split(/\r?\n/).filter(Boolean);
  fs.rmSync(taking, { force: true });
  for (const line of lines) {
    try { next(["--force", ...line.split(" ")]); }
    catch (e) { console.error(`skipped queued "${line}": ${String(e.message).split(/\r?\n/)[0]}`); }
  }
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

function plan(dir, requested = null) {
  const meta = JSON.parse(fs.readFileSync(path.join(dir, "pr.json"), "utf8"));
  if (meta.local) throw new Error(`${dir} reviews a local branch; there is nothing to post to`);
  const v = JSON.parse(fs.readFileSync(path.join(dir, "verified.json"), "utf8"));
  validateVerdict(v);
  const threads = JSON.parse(fs.readFileSync(path.join(dir, "threads.json"), "utf8"));
  const anchors = anchorable(fs.readFileSync(path.join(dir, "diff.patch"), "utf8"));
  const ownComments = threads.filter((t) => t.own);
  const dropped = [];
  const findings = (v.findings ?? []).filter((f) => {
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
    replies.push({ thread: t.id, comment: t.comments[0].id, kind: r.kind, resolve: ["fixed", "accepted"].includes(r.kind), body: `${text}\n\n${FOOTER}\n${REPLY_MARKER(r.kind)}` });
  }
  const resolved = replies.filter((r) => r.resolve).map((r) => threads.find((t) => t.id === r.thread));
  const awaitsAuthor = findings.length > 0 || replies.some((r) => ["still_open", "rejected"].includes(r.kind));

  const marker = `<!-- auto-review head=${meta.head} round=${meta.round}${requested ? ` requested=${requested}` : ""} -->`;
  const headline = blocking.length
    ? `**${findings.length} finding${findings.length > 1 ? "s" : ""}: ${tally}**${inline.length ? ", inline" : ""}.`
    : `**No blocking issues**${findings.length ? ` (${tally}, the author decides)` : ""}.`;
  const notes = bullets(v.notes);
  const body = [
    `🤖 **Automated review by Claude** · round ${meta.round} · \`${short(meta.head)}\``,
    "",
    headline,
    ...(unanchored.length ? ["", "**Not anchorable inline**", ...unanchored.flatMap((f) => [listItem(f), `  - **Scenario:** ${f.scenario}`, `  - **Fix:** ${f.fix}`])] : []),
    ...(resolved.length ? ["", "**Resolved since the last round**", ...resolved.map((t) => `- \`${t.path}${t.line ? `:${t.line}` : ""}\``)] : []),
    ...(notes.length ? ["", "**Notes**", ...notes] : []),
    ...(awaitsAuthor ? ["", RE_REQUEST] : []),
    ...(findings.length ? ["", LEGEND] : []),
    ...(blocking.length ? [] : ["", `@${ME} for the human pass.`]),
    "",
    marker,
  ].join("\n");
  return { meta, body, ready: !blocking.length, tally, inline: inline.map((f) => ({ path: f.file, line: f.line, side: "RIGHT", body: renderFinding(f) })), replies, dropped };
}

function renderPlan(p) {
  const out = [`# ${p.meta.repo}#${p.meta.number} round ${p.meta.round} at ${short(p.meta.head)}: COMMENTED review`, "", "## Body", "", p.body];
  for (const c of p.inline) out.push("", `## Inline ${c.path}:${c.line}`, "", c.body);
  for (const r of p.replies) out.push("", `## Reply to comment ${r.comment}${r.resolve ? " (then resolve)" : ""}`, "", r.body);
  if (p.dropped.length) out.push("", "## Not posted", "", ...p.dropped.map((d) => `- ${d.why}: ${d.f ? `${where(d.f)} ${d.f.defect}` : `${d.r.kind} on ${d.r.thread_id}`}`));
  return out.join("\n");
}

function postArgs(args) {
  const i = args.indexOf("--requested");
  const requested = i < 0 || args[i + 1] === "-" ? null : args[i + 1];
  return { dir: args.find((a, j) => !a.startsWith("--") && args[j - 1] !== "--requested"), requested, dry: args.includes("--dry-run") };
}

async function post(args) {
  const { dir, requested, dry } = postArgs(args);
  const p = plan(dir, requested);
  const rendered = renderPlan(p);
  fs.writeFileSync(path.join(dir, "post.md"), rendered);
  if (dry) {
    console.log(rendered);
    console.log(`\n(dry run: nothing posted; ${path.join(dir, "post.md")})`);
    return;
  }
  const { repo, number, head, round } = p.meta;
  const posted = markersOf(repo, number).find((m) => m.round >= round);
  if (posted) throw new Error(`round ${posted.round} is already posted (head ${short(posted.head)}); not posting round ${round} twice`);
  for (const r of p.replies) {
    const payload = path.join(dir, `reply-${r.comment}.json`);
    fs.writeFileSync(payload, JSON.stringify({ body: r.body }));
    gh("api", "--method", "POST", `repos/${repo}/pulls/${number}/comments/${r.comment}/replies`, "--input", payload);
    if (r.resolve) gh("api", "graphql", "-f", "query=mutation($id:ID!){resolveReviewThread(input:{threadId:$id}){thread{isResolved}}}", "-F", `id=${r.thread}`);
  }
  const payload = path.join(dir, "review.json");
  fs.writeFileSync(payload, JSON.stringify({ commit_id: head, event: "COMMENT", body: p.body, comments: p.inline }));
  console.log(JSON.parse(gh("api", "--method", "POST", `repos/${repo}/pulls/${number}/reviews`, "--input", payload)).html_url);
  if (p.ready) await notifyReady(p);
}

async function notifyReady(p) {
  const { repo, number, round, title, url } = p.meta;
  const link = url ?? `https://github.com/${repo}/pull/${number}`;
  const summary = `Round ${round}: no blocking issues${p.tally ? ` (${p.tally}, the author decides)` : ""}.`;
  await slack({ repo, pr: String(number), title: title ?? "", url: link, summary },
    `[${repo.split("/")[1]}#${number}](${link}) ${title ?? ""}: ${summary}`);
}

async function alert([title, ...text]) {
  const summary = text.join(" ").split(/\r?\n/)[0];
  const last = readJson(ALERTED);
  if (last?.text === summary && Date.now() - last.at < ALERT_QUIET_MS) return console.log(`already alerted at ${new Date(last.at).toISOString()}: ${summary}`);
  fs.mkdirSync(HOME, { recursive: true });
  fs.writeFileSync(ALERTED, JSON.stringify({ at: Date.now(), text: summary }));
  await slack({ repo: "auto-review", pr: "-", title, url: "https://github.com/pulls/review-requested", summary }, `**${title}** ${summary}`);
}

async function slack(fields, dm) {
  if (!fs.existsSync(WEBHOOK_FILE)) return console.log(`DM: ${dm}`);
  try {
    const res = await fetch(fs.readFileSync(WEBHOOK_FILE, "utf8").trim(), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(fields),
    });
    if (res.ok) return console.log("Slack workflow notified");
    console.log(`Slack workflow answered ${res.status}: ${(await res.text()).slice(0, 200)}`);
  } catch (e) {
    console.log(`Slack workflow failed: ${e.message}`);
  }
  console.log(`DM: ${dm}`);
}

function lock([token]) {
  fs.mkdirSync(HOME, { recursive: true });
  const mine = token ?? crypto.randomUUID();
  for (;;) {
    try {
      fs.writeFileSync(LOCK, JSON.stringify({ at: Date.now(), token: mine }), { flag: "wx" });
      return console.log(mine);
    } catch (e) {
      if (e.code !== "EEXIST") throw e;
    }
    let held;
    try { held = readJson(LOCK); } catch { held = { at: Date.now() }; }
    if (token && held?.token === token) {
      fs.writeFileSync(LOCK, JSON.stringify({ at: Date.now(), token }));
      return console.log(token);
    }
    if (held && Date.now() - held.at < LOCK_TTL_MS) {
      console.error(`another run holds the lock since ${new Date(held.at).toISOString()}`);
      process.exit(3);
    }
    fs.rmSync(LOCK, { force: true });
  }
}

function unlock([token]) {
  if (fs.existsSync(QUEUE) && fs.statSync(QUEUE).size) {
    console.log("PRs are queued: review what take prints, then unlock again");
    process.exit(4);
  }
  if (readJson(LOCK)?.token === token) fs.rmSync(LOCK, { force: true });
}

const [verb, ...rest] = process.argv.slice(2);
const verbs = {
  lock, unlock, queue, take, candidates, next, post, alert,
  plan: (a) => console.log(renderPlan(plan(postArgs(a).dir, postArgs(a).requested))),
  notify: (a) => notifyReady(plan(a[0])),
};
if (!verbs[verb]) {
  console.error("usage: auto-review.mjs lock [<token>] | unlock <token> | queue [dry-run] [deep] <PR>... | take | candidates [--force] [<PR>...] | next [--force] [dry-run] [deep] [<PR>...] | post <run dir> [--requested <time|->] [--dry-run] | plan <run dir> [--requested <time|->] | notify <run dir> | alert <title> <text>");
  process.exit(2);
}
try {
  await verbs[verb](rest);
} catch (e) {
  console.error(e.stderr ? `${e.message}\n${e.stderr}` : e.message);
  process.exit(1);
}
