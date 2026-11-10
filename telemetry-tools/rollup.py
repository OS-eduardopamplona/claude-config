import argparse
import csv
import glob
import json
import os
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import backfill
import capacity

HOME = Path.home() / ".claude"
APP_DATA = Path.home() / "AppData" / "Local" / "Claude-Data"
OUT_DIR = HOME / "telemetry" / "rollup"
JIRA_CACHE = HOME / "telemetry" / "jira" / "issues.json"
OTEL_DIR = HOME / "telemetry" / "otel"
PIDS_DIR = HOME / "telemetry" / "pids"
ADO = ["--org", "https://dev.azure.com/OutSystemsRD", "--project", "ArtifactRepository"]
ADO_DEFINITIONS = {"OutSystems/OutSystems.ModelExtensions": 432, "OutSystems/OutSystems.Model": 298}
REPO_ALIASES = {"model": "OutSystems/OutSystems.Model", "me": "OutSystems/OutSystems.ModelExtensions"}
DEFAULT_REPO = "OutSystems/OutSystems.ModelExtensions"
TICKET = re.compile(r"RDMST-\d{3,5}", re.I)
BOT = re.compile(r"\[bot\]$|copilot|bot$|^os-apex", re.I)


def run_json(cmd):
    try:
        cmd = [shutil.which(cmd[0]) or cmd[0], *cmd[1:]]
        out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=120, shell=False)
        return json.loads(out.stdout) if out.returncode == 0 and out.stdout.strip() else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def iso(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def from_ms(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc) if ms else None


def load_metadata():
    sessions = {}
    for f in glob.glob(str(APP_DATA / "*" / "claude-code-sessions" / "*" / "*" / "local_*.json")):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        sessions[d["sessionId"]] = d
    return sessions


def family(sessions, root):
    children = defaultdict(list)
    for s in sessions.values():
        parent = (s.get("spawnedFrom") or {}).get("sessionId")
        if parent:
            children[parent].append(s["sessionId"])
    order, todo = [], [root]
    while todo:
        sid = todo.pop(0)
        if sid in sessions and sid not in order:
            order.append(sid)
            todo.extend(children[sid])
    return order


def pr_ref(text):
    m = re.match(r"\s*(?:([\w.-]+)#)?(\d+)", text)
    if not m:
        return None
    repo = m.group(1)
    if repo is None:
        repo = DEFAULT_REPO
    elif "/" not in repo:
        repo = REPO_ALIASES.get(repo.lower(), f"OutSystems/{repo}")
    return repo, int(m.group(2))


def parse_state(path):
    workers, prs, clouds = {}, defaultdict(set), defaultdict(set)
    if not path or not Path(path).exists():
        return workers, prs, clouds
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.startswith("|") or line.startswith("|---"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        tickets = [t.upper() for c in cells[:2] for t in TICKET.findall(c)]
        if not tickets:
            continue
        ticket = tickets[0]
        for c in cells[1:3]:
            for local in re.findall(r"local_[0-9a-f-]{8,}", c):
                workers[local] = ticket
            for cloud in re.findall(r"session_\w+", c):
                clouds[ticket].add(cloud)
        if not TICKET.search(cells[0]):
            for part in re.split(r"[,(]", cells[0]):
                ref = pr_ref(part)
                if ref:
                    prs[ticket].add(ref)
    return workers, prs, clouds


def ticket_of(s, state_workers, root_ticket):
    sid = s["sessionId"]
    for local, ticket in state_workers.items():
        if sid.startswith(local):
            return ticket
    spawned = s.get("spawnedFrom") or {}
    texts = [s.get("title"), spawned.get("name"), spawned.get("title"), s.get("branch"), s.get("worktreePath")]
    texts += [p.get("branch") for p in s.get("prs") or []]
    found = [t.upper() for x in texts if x for t in TICKET.findall(x)]
    other = [t for t in found if t != root_ticket]
    return other[0] if other else (found[0] if found else None)


def pr_details(repo, number):
    d = run_json(["gh", "pr", "view", str(number), "--repo", repo, "--json",
                  "number,url,title,state,isDraft,createdAt,mergedAt,closedAt,headRefName,author,reviews,commits"])
    if not d:
        return {"repo": repo, "number": number, "error": "gh pr view failed"}
    author = (d.get("author") or {}).get("login")
    reviews = [r for r in d.get("reviews") or [] if (r.get("author") or {}).get("login") != author]
    human = [r for r in reviews if not BOT.search((r.get("author") or {}).get("login") or "")]
    return {
        "repo": repo, "number": number, "url": d["url"], "title": d["title"], "state": d["state"],
        "draft": d["isDraft"], "created": d["createdAt"], "merged": d.get("mergedAt"), "closed": d.get("closedAt"),
        "head": d["headRefName"], "commits": len(d.get("commits") or []),
        "review_rounds": len(human), "changes_requested": sum(r["state"] == "CHANGES_REQUESTED" for r in human),
        "bot_reviews": len(reviews) - len(human),
        "ci": ci_runs(repo, number, d["headRefName"]),
    }


def ci_runs(repo, number, head):
    definition = ADO_DEFINITIONS.get(repo)
    if definition:
        runs = run_json(["az", "pipelines", "runs", "list", *ADO, "--pipeline-ids", str(definition),
                         "--branch", f"refs/pull/{number}/merge", "--top", "200", "--query",
                         "[].{id:id,result:result,status:status,start:startTime,finish:finishTime,sha:triggerInfo.\"pr.sourceSha\"}",
                         "-o", "json"]) or []
        source = "ado"
    else:
        raw = run_json(["gh", "run", "list", "--repo", repo, "--branch", head, "--limit", "200", "--json",
                        "databaseId,conclusion,status,createdAt,updatedAt,headSha,attempt"]) or []
        runs = [{"id": r["databaseId"], "result": r["conclusion"], "status": r["status"], "start": r["createdAt"],
                 "finish": r["updatedAt"], "sha": r["headSha"], "attempt": r.get("attempt", 1)} for r in raw]
        source = "github-actions"
    minutes = sum((iso(r["finish"]) - iso(r["start"])).total_seconds() / 60
                  for r in runs if r.get("start") and r.get("finish"))
    shas = {r.get("sha") for r in runs if r.get("sha")}
    reruns = len(runs) - len(shas) + sum(max(r.get("attempt", 1) - 1, 0) for r in runs)
    return {
        "source": source, "runs": len(runs), "minutes": round(minutes, 1), "reruns": max(reruns, 0),
        "failed": sum(r.get("result") in ("failed", "failure") for r in runs),
        "canceled": sum(r.get("result") in ("canceled", "cancelled") for r in runs),
    }


def otel_by_session():
    totals = defaultdict(lambda: defaultdict(float))
    for f in OTEL_DIR.glob("metrics-*.jsonl"):
        for line in open(f, encoding="utf-8"):
            payload = json.loads(line)["payload"]
            for rm in payload.get("resourceMetrics", []):
                for sm in rm.get("scopeMetrics", []):
                    for m in sm.get("metrics", []):
                        points = (m.get("sum") or m.get("gauge") or {}).get("dataPoints", [])
                        for p in points:
                            attrs = {a["key"]: next(iter(a["value"].values())) for a in p.get("attributes", [])}
                            sid = attrs.get("session.id")
                            if sid:
                                value = p.get("asDouble", p.get("asInt", 0))
                                totals[sid][m["name"]] += float(value)
    return totals


def jira_cache():
    if not JIRA_CACHE.exists():
        return {}, None
    d = json.load(open(JIRA_CACHE, encoding="utf-8"))
    return d.get("issues", {}), d.get("fetched_at")


def resolve_root(meta, arg):
    if arg != "self":
        return next((k for k in meta if k.startswith(arg)), None)
    host = os.environ.get("CLAUDE_CODE_HOST_SESSION_ID")
    if host in meta:
        return host
    pid_file = PIDS_DIR / f"{os.environ.get('CLAUDE_PID', '')}.json"
    if os.environ.get("CLAUDE_PID") and pid_file.exists():
        try:
            host = json.load(open(pid_file, encoding="utf-8")).get("host_session")
        except (OSError, ValueError):
            host = None
        if host in meta:
            return host
    cli = os.environ.get("CLAUDE_CODE_SESSION_ID")
    return next((k for k, s in meta.items() if cli and cli in (s.get("cliSessionId"), s.get("lastAssistantCliSessionId"))), None)


def repo_of(path):
    path = capacity.native_path(path)
    if not path:
        return "unknown"
    path = re.split(r"[\\/]\.claude[\\/]worktrees[\\/]", path, flags=re.I)[0]
    return Path(path).name or path


def family_root(meta, sid):
    seen = set()
    while sid not in seen:
        seen.add(sid)
        parent = (meta.get(sid, {}).get("spawnedFrom") or {}).get("sessionId")
        if not parent or parent not in meta:
            return sid
        sid = parent
    return sid


def group_of(meta, sid, s, group, state_workers):
    if group == "repo":
        return repo_of(s.get("worktreePath") or s.get("cwd") or s.get("originCwd"))
    if group == "family":
        top = family_root(meta, sid)
        own = ticket_of(meta[top], state_workers, None) if top in meta else None
        return f"{own or (meta.get(top) or {}).get('title') or top} [{top[6:14] if top.startswith('local_') else top[:8]}]"
    return ticket_of(s, state_workers, None) or "unmapped"


def resource_notes(activity_minutes, sampled, attributed, first_sample):
    if sampled and int(datetime.now(timezone.utc).timestamp() // 60) - max(sampled) <= 2:
        activity_minutes = {m for m in activity_minutes if m <= max(sampled)}
    active = len(activity_minutes)
    if not active:
        return None
    covered = activity_minutes & sampled
    seen = activity_minutes & attributed
    before = sum(1 for m in activity_minutes if first_sample is None or m < first_sample)
    if not seen:
        if before == active:
            why = "before the sampler started" + (f" ({datetime.fromtimestamp(first_sample * 60, timezone.utc):%Y-%m-%d %H:%M} UTC)" if first_sample else "")
        elif not covered:
            why = "the sampler wrote nothing while it ran (receiver down)"
        else:
            why = "its processes were never attributed to it (CLI not mapped to the session)"
        return f"not measured: {why}"
    if len(seen) < active * 0.9:
        rest = []
        if before:
            rest.append(f"{before} before the sampler started")
        if active - before - len(covered & seen) > 0 and len(covered) < active - before:
            rest.append(f"{active - before - len(covered)} with the receiver down")
        return f"partly measured: {len(seen)} of {active} active minutes sampled" + (f" ({', '.join(rest)})" if rest else "")
    return None


def print_report(result):
    def fmt(v, unit=""):
        return "not measured" if v is None else f"{v}{unit}"
    print(f"# {result['title']}\nwindow {result['since'] or 'all time'} to {result['generated_at']:%Y-%m-%d %H:%M} UTC\n")
    for r in result["tickets"]:
        tk = r["tokens"]
        res = r["resources"] or {}
        print(f"## {r['ticket']}{' (root)' if r.get('root') else ''}: {r['summary'] or (r['session_detail'][0]['title'] if r['session_detail'] else '')}")
        print(f"- sessions {r['sessions']} local, {r['cloud_sessions']} cloud | ${r['cost_usd']} | {r['requests']} requests | "
              f"{sum(tk.values()):,} tokens ({tk['cache_read']:,} cache read, {tk['output']:,} output)")
        print(f"- active {r['active_min']} min | wall {fmt(r['wall_hours'], ' h')} | build+test {r['build_test_min']} min")
        cats = sorted(((k, c["seconds"] + c["bg_seconds"], c["calls"] + c["bg_calls"]) for k, c in (r["tool_time"] or {}).get("by_category", {}).items()), key=lambda x: -x[1])
        print("- tool time: " + (", ".join(f"{k} {s / 60:.1f} min/{n} calls" for k, s, n in cats if n) or "none"))
        if res:
            print(f"- CPU {res['cpu_hours']} h (avg {res['avg_cores']} cores) | peak RAM {res['peak_rss_gb']} GB | IO {res['io_read_gb']} GB read, {res['io_write_gb']} GB written | {res['sampled_min']} min sampled")
        for note in r["resources_notes"] or ([] if res else ["not measured"]):
            print(f"- resources {note}")
        print(f"- disk {fmt((r['disk_gb'] or {}).get('total'), ' GB')} | CI {r['ci_runs']} runs, {r['ci_minutes']} min, {r['ci_reruns']} reruns, {r['ci_failed']} failed | {r['review_rounds']} human review rounds")
        for p in r["prs"]:
            print(f"- PR {p['repo']}#{p['number']} {p.get('state', '?')}{' draft' if p.get('draft') else ''} {p.get('url', '')}")
        print()


def main():
    ap = argparse.ArgumentParser(description="One row per ticket for a session and every session it started, or for every session on the machine.")
    pick = ap.add_mutually_exclusive_group(required=True)
    pick.add_argument("--root", help="local_ session id (prefix accepted), or 'self' for the session running this")
    pick.add_argument("--all", action="store_true", help="every session on the machine active since --since")
    ap.add_argument("--group", choices=("ticket", "repo", "family"), default="ticket", help="--all rows: by ticket, repo or family")
    ap.add_argument("--state", help="orchestrator state file (read only)")
    ap.add_argument("--root-ticket", default=None, help="the epic the orchestrator works, e.g. RDMST-5555")
    ap.add_argument("--since", help="UTC date or datetime; tokens before it are not counted (default: the root's start)")
    ap.add_argument("--no-remote", action="store_true", help="skip gh and az")
    ap.add_argument("--resources", help="folder of the resource sampler's samples-*.jsonl (default telemetry/resources)")
    ap.add_argument("--no-disk", action="store_true", help="skip measuring worktree sizes")
    ap.add_argument("--report", action="store_true", help="also print a Markdown summary to stdout")
    ap.add_argument("--out", help="JSON output path")
    a = ap.parse_args()
    started = datetime.now(timezone.utc)

    meta = load_metadata()
    state_workers, state_prs, state_clouds = parse_state(a.state)
    if a.all:
        if not a.since:
            sys.exit("--all needs --since")
        root, root_ticket, root_own = None, a.root_ticket, None
        since = backfill.parse_date(a.since)
        members = [k for k, s in meta.items() if (from_ms(s.get("lastActivityAt")) or since) >= since]
    else:
        root = resolve_root(meta, a.root)
        if not root:
            sys.exit(f"no session {a.root}")
        root_ticket = a.root_ticket or (TICKET.findall(meta[root].get("title") or "") or [None])[0]
        members = family(meta, root)
        root_own = ticket_of(meta[root], state_workers, None) or a.root_ticket
        since = backfill.parse_date(a.since) if a.since else from_ms(meta[root].get("createdAt"))
    mode = "all" if a.all else ("family" if len(members) > 1 else "session")

    cli_to_local = {}
    for sid in members:
        for key in ("cliSessionId", "lastAssistantCliSessionId"):
            if meta[sid].get(key):
                cli_to_local[meta[sid][key]] = sid
    found = backfill.scan_full(since, None if a.all else set(cli_to_local))
    usage = {r["session"]: r for r in backfill.aggregate(found["messages"], found["tools"])}
    if a.all:
        for cli, r in usage.items():
            if cli not in cli_to_local:
                cli_to_local[cli] = cli
                meta[cli] = {"sessionId": cli, "cliSessionId": cli, "title": f"CLI session {cli[:8]} (no desktop record)",
                             "cwd": r.get("cwd"), "branch": r.get("branch")}
                members.append(cli)
    otel = otel_by_session()
    now = datetime.now(timezone.utc)
    lo = capacity.window(since, found["activity"])
    samples = capacity.load_samples(a.resources, lo, now)
    minutes = capacity.session_minutes(samples, members, cli_to_local)
    first_sample = capacity.first_sample_minute(a.resources)
    sampled = {m for s in samples for m in range(int((s["_ts"].timestamp() - s["_interval"]) // 60), int(s["_ts"].timestamp() // 60) + 1)}
    session_activity = defaultdict(set)
    for c, ms in found["activity"].items():
        if c in cli_to_local:
            session_activity[cli_to_local[c]].update(ms)
    attributed = {sid: {m for i in mm for m in range(int((samples[i]["_ts"].timestamp() - samples[i]["_interval"]) // 60), int(samples[i]["_ts"].timestamp() // 60) + 1)}
                  for sid, mm in minutes.items()}
    known_roots, worktrees = {}, {}
    for sid in members:
        own = capacity.worktree_of(meta[sid].get("worktreePath") or meta[sid].get("cwd"))
        used = capacity.worktree_roots(
            [x for c in (meta[sid].get("cliSessionId"), meta[sid].get("lastAssistantCliSessionId")) if c
             for x in found["paths"].get(c, ())], known_roots)
        worktrees[sid] = sorted(({own} if own else set()) | used)
    disk = {} if a.no_disk else capacity.disk_usage(sorted({w for ws in worktrees.values() for w in ws}))

    tickets = defaultdict(lambda: {"sessions": [], "prs": set(), "clouds": set()})
    for sid in members:
        s = meta[sid]
        if a.all:
            ticket = group_of(meta, sid, s, a.group, state_workers)
        elif sid == root:
            ticket = root_own or ("orchestration" if mode == "family" else "unmapped")
        else:
            ticket = ticket_of(s, state_workers, root_ticket) or "unmapped"
        if sid == root:
            tickets[ticket]["root"] = True
        cli_ids = {s.get("cliSessionId"), s.get("lastAssistantCliSessionId")} - {None}
        rows = [usage[c] for c in cli_ids if c in usage]
        o = defaultdict(float)
        for c in cli_ids:
            for k, v in otel.get(c, {}).items():
                o[k] += v
        tickets[ticket]["sessions"].append({
            "local_id": sid, "cli_ids": sorted(cli_ids), "title": s.get("title"),
            "name": (s.get("spawnedFrom") or {}).get("name"), "model": s.get("model"),
            "created": from_ms(s.get("createdAt")), "last_activity": from_ms(s.get("lastActivityAt")),
            "archived": s.get("isArchived"), "turns": s.get("completedTurns"),
            "requests": sum(r["requests"] for r in rows),
            "tokens": {k: sum(r[k] for r in rows) for k in backfill.TOKEN_FIELDS},
            "cost_usd": round(sum(r["cost_usd"] for r in rows), 4),
            "active_min": round(sum(r["active_min"] for r in rows), 1),
            "otel_cost_usd": round(o.get("claude_code.cost.usage", 0), 4) or None,
            "otel_active_min": round(o.get("claude_code.active_time.total", 0) / 60, 1) or None,
            "where": "local", "cwd": s.get("cwd"), "worktrees": worktrees.get(sid, []),
            "tool_time": backfill.merge_tool_time(r.get("tool_time") for r in rows),
            "resources": capacity.summarize_minutes([minutes.get(sid, {})]),
            "resources_note": resource_notes(session_activity.get(sid, set()), sampled, attributed.get(sid, set()), first_sample),
            "disk_gb": None if a.no_disk else capacity.disk_total(worktrees.get(sid, []), disk),
        })
        for p in s.get("prs") or []:
            if p.get("repo") and p.get("prNumber"):
                repo = p["repo"] if "/" in p["repo"] else f"OutSystems/{p['repo']}"
                tickets[ticket]["prs"].add((repo, int(p["prNumber"])))
        for c in s.get("cloudSpawnedTasks") or []:
            child_ticket = ticket_of({"sessionId": "", "title": c.get("title") or ""}, {}, root_ticket)
            tickets[child_ticket or ticket]["clouds"].add(c.get("sessionId"))
    for ticket, refs in state_prs.items():
        tickets[ticket]["prs"].update(refs)
    for ticket, clouds in state_clouds.items():
        tickets[ticket]["clouds"].update(clouds)

    all_prs = sorted({ref for t in tickets.values() for ref in t["prs"]})
    pr_info = {}
    if not a.no_remote:
        with ThreadPoolExecutor(8) as pool:
            pr_info = dict(zip(all_prs, pool.map(lambda r: pr_details(*r), all_prs)))
    for ref in all_prs:
        info = pr_info.get(ref, {})
        named = [t.upper() for x in (info.get("head"), info.get("title")) if x for t in TICKET.findall(x)]
        owners = [t for t in tickets if ref in tickets[t]["prs"]]
        owner = next((t for t in named if t in tickets), None) or next((t for t in owners if not tickets[t].get("root")), owners[0])
        tickets[owner]["prs"].add(ref)
        for t in owners:
            if t != owner:
                tickets[t]["prs"].discard(ref)
    issues, jira_fetched = jira_cache()

    out_rows = []
    for ticket, t in tickets.items():
        ss = t["sessions"]
        active = [x for x in ss if x["requests"] or (since and x["last_activity"] and x["last_activity"] >= since)]
        if since and not active and not t["clouds"]:
            continue
        prs = [pr_info.get(r, {"repo": r[0], "number": r[1]}) for r in sorted(t["prs"])]
        issue = issues.get(ticket, {})
        created = [x["created"] for x in ss if x["created"]]
        last = [x["last_activity"] for x in ss if x["last_activity"]]
        jira_created, jira_resolved = iso(issue.get("created")), iso(issue.get("resolutiondate"))
        tt = backfill.merge_tool_time(x["tool_time"] for x in ss)
        clouds = t["clouds"] - {None}
        out_rows.append({
            "ticket": ticket, "root": bool(t.get("root")), "summary": issue.get("summary"), "jira_status": issue.get("status"),
            "jira_category": issue.get("status_category"),
            "jira_cycle_days": round(((jira_resolved or now) - jira_created).total_seconds() / 86400, 2) if jira_created else None,
            "jira_status_since": issue.get("statuscategorychangedate"),
            "sessions": len(ss), "cloud_sessions": len(clouds),
            "where": {"local": len(ss), "cloud": len(clouds)},
            "tool_time": tt, "build_test_min": round(backfill.build_test_seconds(tt) / 60, 1),
            "resources": capacity.summarize_minutes([minutes.get(x["local_id"], {}) for x in ss]),
            "resources_notes": sorted({f"{x['title'] or x['local_id']}: {x['resources_note']}" if len(ss) > 1 else x["resources_note"]
                                       for x in ss if x["resources_note"]}) + ([f"{len(clouds)} cloud session{'s' if len(clouds) > 1 else ''}: not measured, no local resource data"] if clouds else []),
            "disk_gb": None if a.no_disk else capacity.disk_total([w for x in ss for w in x["worktrees"]], disk),
            "requests": sum(x["requests"] for x in ss),
            "tokens": {k: sum(x["tokens"][k] for x in ss) for k in backfill.TOKEN_FIELDS},
            "cost_usd": round(sum(x["cost_usd"] for x in ss), 2),
            "active_min": round(sum(x["active_min"] for x in ss), 1),
            "wall_hours": round((max(last) - min(created)).total_seconds() / 3600, 2) if created and last else None,
            "first_session": min(created) if created else None,
            "prs": prs,
            "pr_state": ", ".join(f"{p.get('state', '?')}{' draft' if p.get('draft') else ''}" for p in prs) or None,
            "ci_runs": sum((p.get("ci") or {}).get("runs", 0) for p in prs),
            "ci_minutes": round(sum((p.get("ci") or {}).get("minutes", 0) for p in prs), 1),
            "ci_reruns": sum((p.get("ci") or {}).get("reruns", 0) for p in prs),
            "ci_failed": sum((p.get("ci") or {}).get("failed", 0) for p in prs),
            "review_rounds": sum(p.get("review_rounds", 0) for p in prs),
            "session_detail": ss, "cloud_ids": sorted(t["clouds"] - {None}),
        })
    out_rows.sort(key=lambda r: (r["root"] and len(out_rows) > 1, -r["cost_usd"]))
    kept_local = {x["local_id"] for r in out_rows for x in r["session_detail"]}
    kept_clouds = {c for r in out_rows for c in r["cloud_ids"]}
    merged_activity = {}
    for c, m in found["activity"].items():
        if cli_to_local.get(c) in kept_local:
            merged_activity.setdefault(cli_to_local[c], set()).update(m)
    cloud_spans = {c: span for c, span in found["mentions"].items() if c in kept_clouds}
    conc = capacity.concurrency(merged_activity, cloud_spans, lo, now)
    machine = capacity.machine_from_samples(samples)
    family_tools = backfill.merge_tool_time(x["tool_time"] for r in out_rows for x in r["session_detail"])
    disk_family = None if a.no_disk else capacity.disk_total([w for r in out_rows for x in r["session_detail"] for w in x["worktrees"]], disk)
    footprint = (machine or {}).get("per_session_minute")
    result_capacity = {
        "machine": capacity.machine_spec(),
        "window": {"start": lo.isoformat(), "end": now.isoformat()},
        "concurrency": conc,
        "scope": "every session on this machine in the window" if a.all else "this session and every session it started",
        "cloud_activity": "estimated: each cloud session counts from its first to its last mention in the transcripts",
        "resources": machine,
        "family_resources": capacity.summarize_minutes([minutes.get(x, {}) for x in kept_local]),
        "tool_time": family_tools,
        "build_test_hours": round(backfill.build_test_seconds(family_tools) / 3600, 2),
        "worktree_disk_gb": disk_family,
        "ci_minutes_offloaded": round(sum(r["ci_minutes"] for r in out_rows), 1),
        "sizing": capacity.sizing(conc, footprint, disk_family),
    }
    root_title = meta[root].get("title") if root else None
    label = root_ticket or root_own
    title = (f"All sessions by {a.group}" if mode == "all" else f"{label or root_title or root} Ledger" if mode == "family"
             else f"{label} Session" if label else root_title or root)
    result = {
        "generated_at": now, "mode": mode, "group": a.group if a.all else None, "title": title,
        "root": root, "root_title": root_title, "root_ticket": root_ticket, "root_row": root_own,
        "children": len(members) - 1 if root else None,
        "since": a.since or since.strftime("%Y-%m-%dT%H:%MZ"), "jira_fetched_at": jira_fetched, "tickets": out_rows, "capacity": result_capacity,
        "gaps": ["cloud sessions have no local transcripts or OTel; counted, not costed",
                 "cost is estimated from list prices; OTel cost appears per session once exporting",
                 "active time is assistant activity with gaps capped at 5 min; OTel active time when present",
                 "Jira cycle time is created to resolution (or now); no changelog transitions",
                 "resources come only from the sampler's start onward"
                 + (f" (first sample {machine['first_sample'][:16]} UTC)" if machine else " (no samples yet: not measured)"),
                 "cloud sessions have no resource data; their concurrency is a first-to-last-mention estimate",
                 "processes shorter than 15 s are partly missed by the once-a-minute sampler",
                 "tool time is wall time from tool call to result, not CPU; parallel calls overlap",
                 "worktree disk counts the session's .claude/worktrees folder and the git worktrees its shell commands cd, -C or worktree-add into, that still exist; a worktree two tickets used counts in both rows and once in the family total",
                 f"foreground shell calls longer than {backfill.SHELL_FG_CAP_S} s are capped there: the tool times out at 10 min, so the rest is a permission or user wait"],
        "run_seconds": None,
    }
    result["run_seconds"] = round((datetime.now(timezone.utc) - started).total_seconds(), 1)
    out = Path(a.out or OUT_DIR / (f"all-{a.group}-{a.since[:10]}.json" if a.all else f"{root}.json"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")
    with open(out.with_suffix(".csv"), "w", newline="", encoding="utf-8") as f:
        cols = ["ticket", "summary", "jira_status", "sessions", "cloud_sessions", "requests", "cost_usd", "active_min",
                "wall_hours", "ci_runs", "ci_minutes", "ci_reruns", "ci_failed", "review_rounds", "pr_state", "jira_cycle_days",
                "build_test_min", "cpu_hours", "peak_rss_gb", "disk_gb", "resources_notes"]
        w = csv.DictWriter(f, cols, extrasaction="ignore")
        w.writeheader()
        w.writerows({**r, "cpu_hours": (r["resources"] or {}).get("cpu_hours", "not measured"),
                     "peak_rss_gb": (r["resources"] or {}).get("peak_rss_gb", "not measured"),
                     "resources_notes": "; ".join(r["resources_notes"]),
                     "disk_gb": (r["disk_gb"] or {}).get("total")} for r in out_rows)
    if a.report:
        print_report(result)
    print(f"{len(out_rows)} rows, ${sum(r['cost_usd'] for r in out_rows):,.2f} in {result['run_seconds']} s -> {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
