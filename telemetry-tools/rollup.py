import argparse
import csv
import glob
import json
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

HOME = Path.home() / ".claude"
APP_DATA = Path.home() / "AppData" / "Local" / "Claude-Data"
OUT_DIR = HOME / "telemetry" / "rollup"
JIRA_CACHE = HOME / "telemetry" / "jira" / "issues.json"
OTEL_DIR = HOME / "telemetry" / "otel"
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


def main():
    ap = argparse.ArgumentParser(description="One row per ticket for an orchestrator session's family.")
    ap.add_argument("--root", required=True, help="orchestrator local_ session id (prefix accepted)")
    ap.add_argument("--state", help="orchestrator state file (read only)")
    ap.add_argument("--root-ticket", default=None, help="the epic the orchestrator works, e.g. RDMST-5555")
    ap.add_argument("--since", help="UTC date; tokens before it are not counted")
    ap.add_argument("--no-remote", action="store_true", help="skip gh and az")
    ap.add_argument("--out", help="JSON output path")
    a = ap.parse_args()

    meta = load_metadata()
    root = next((k for k in meta if k.startswith(a.root)), None)
    if not root:
        sys.exit(f"no session {a.root}")
    root_ticket = a.root_ticket or (TICKET.findall(meta[root].get("title") or "") or [None])[0]
    state_workers, state_prs, state_clouds = parse_state(a.state)
    members = family(meta, root)
    since = backfill.parse_date(a.since)

    cli_to_local = {}
    for sid in members:
        for key in ("cliSessionId", "lastAssistantCliSessionId"):
            if meta[sid].get(key):
                cli_to_local[meta[sid][key]] = sid
    usage = {r["session"]: r for r in backfill.aggregate(backfill.scan(since, set(cli_to_local)))}
    otel = otel_by_session()

    tickets = defaultdict(lambda: {"sessions": [], "prs": set(), "clouds": set()})
    for sid in members:
        s = meta[sid]
        ticket = "orchestration" if sid == root else (ticket_of(s, state_workers, root_ticket) or "unmapped")
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
        owner = next((t for t in named if t in tickets), None) or next((t for t in owners if t != "orchestration"), owners[0])
        tickets[owner]["prs"].add(ref)
        for t in owners:
            if t != owner:
                tickets[t]["prs"].discard(ref)
    issues, jira_fetched = jira_cache()
    now = datetime.now(timezone.utc)

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
        out_rows.append({
            "ticket": ticket, "summary": issue.get("summary"), "jira_status": issue.get("status"),
            "jira_category": issue.get("status_category"),
            "jira_cycle_days": round(((jira_resolved or now) - jira_created).total_seconds() / 86400, 2) if jira_created else None,
            "jira_status_since": issue.get("statuscategorychangedate"),
            "sessions": len(ss), "cloud_sessions": len(t["clouds"] - {None}),
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
    out_rows.sort(key=lambda r: (r["ticket"] == "orchestration", -r["cost_usd"]))
    result = {
        "generated_at": now, "root": root, "root_title": meta[root].get("title"), "root_ticket": root_ticket,
        "since": a.since, "jira_fetched_at": jira_fetched, "tickets": out_rows,
        "gaps": ["cloud sessions have no local transcripts or OTel; counted, not costed",
                 "cost is estimated from list prices; OTel cost appears per session once exporting",
                 "active time is assistant activity with gaps capped at 5 min; OTel active time when present",
                 "Jira cycle time is created to resolution (or now); no changelog transitions"],
    }
    out = Path(a.out or OUT_DIR / f"{root}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")
    with open(out.with_suffix(".csv"), "w", newline="", encoding="utf-8") as f:
        cols = ["ticket", "summary", "jira_status", "sessions", "cloud_sessions", "requests", "cost_usd", "active_min",
                "wall_hours", "ci_runs", "ci_minutes", "ci_reruns", "ci_failed", "review_rounds", "pr_state", "jira_cycle_days"]
        w = csv.DictWriter(f, cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(out_rows)
    print(f"{len(out_rows)} tickets, ${sum(r['cost_usd'] for r in out_rows):,.2f} -> {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
