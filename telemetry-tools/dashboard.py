import argparse
import json
import sys
from pathlib import Path

HOME = Path.home() / ".claude"
ROLLUP_DIR = HOME / "telemetry" / "rollup"
OUT_DIR = HOME / "telemetry" / "dashboard"
TEMPLATE = Path(__file__).with_name("dashboard.html")


def tool_hours(tt):
    if not tt:
        return None
    return {k: {"fg": round(c["seconds"] / 3600, 2), "bg": round(c["bg_seconds"] / 3600, 2), "calls": c["calls"],
                "bgCalls": c["bg_calls"], "capped": c.get("capped", 0), "unfinished": c["unfinished"]}
            for k, c in tt["by_category"].items()}


def resources(r):
    if not r:
        return None
    return {"cpuH": r["cpu_hours"], "avgCores": r["avg_cores"], "peakRamGb": r["peak_rss_gb"],
            "ioGb": round((r["io_read_gb"] or 0) + (r["io_write_gb"] or 0), 2), "sampledMin": r["sampled_min"],
            "top": r["top"][:5]}


def slim_capacity(c):
    if not c:
        return None
    tt = c.get("tool_time") or {}
    return {
        "machine": c.get("machine"), "window": c.get("window"), "concurrency": c.get("concurrency"),
        "cloudNote": c.get("cloud_activity"), "resources": c.get("resources"),
        "familyResources": resources(c.get("family_resources")), "toolTime": tool_hours(tt),
        "longest": tt.get("longest"), "background": tt.get("background"), "capped": tt.get("capped", 0),
        "buildTestHours": c.get("build_test_hours"), "disk": c.get("worktree_disk_gb"),
        "ciMinutes": c.get("ci_minutes_offloaded"), "sizing": c.get("sizing"),
    }


def slim(rollup):
    tickets = []
    for t in rollup["tickets"]:
        tickets.append({
            "key": t["ticket"], "root": t.get("root", t["ticket"] == "orchestration"),
            "resNotes": t.get("resources_notes") or [], "summary": t.get("summary"), "status": t.get("jira_status"),
            "category": t.get("jira_category"), "cycle": t.get("jira_cycle_days"),
            "sessions": t["sessions"], "cloud": t["cloud_sessions"], "requests": t["requests"],
            "tokens": t["tokens"], "cost": t["cost_usd"], "active": t["active_min"], "wall": t["wall_hours"],
            "ciRuns": t["ci_runs"], "ciMin": t["ci_minutes"], "ciReruns": t["ci_reruns"], "ciFailed": t["ci_failed"],
            "reviews": t["review_rounds"],
            "where": t.get("where") or {"local": t["sessions"], "cloud": t["cloud_sessions"]},
            "buildTestMin": t.get("build_test_min"), "toolTime": tool_hours(t.get("tool_time")),
            "res": resources(t.get("resources")), "disk": t.get("disk_gb"),
            "prs": [{
                "ref": ("" if p["repo"].endswith("ModelExtensions") else p["repo"].split("/")[1].replace("OutSystems.", "")) + f"#{p['number']}",
                "url": p.get("url"), "title": p.get("title"), "state": p.get("state"), "draft": p.get("draft"),
                "reviews": p.get("review_rounds"), "ci": p.get("ci"),
            } for p in t["prs"]],
            "spans": [{
                "title": s.get("title"), "start": s.get("created"), "end": s.get("last_activity"),
                "cost": s.get("cost_usd"), "active": s.get("active_min"), "requests": s.get("requests"),
            } for s in t["session_detail"]],
        })
    return {
        "generatedAt": rollup["generated_at"], "since": rollup.get("since"), "root": rollup["root"],
        "rootTitle": rollup.get("root_title"), "rootTicket": rollup.get("root_ticket"),
        "mode": rollup.get("mode", "family"), "group": rollup.get("group"), "title": title_of(rollup),
        "jiraFetchedAt": rollup.get("jira_fetched_at"), "gaps": rollup.get("gaps", []), "tickets": tickets,
        "capacity": slim_capacity(rollup.get("capacity")),
    }


def title_of(rollup):
    return rollup.get("title") or f"{rollup.get('root_ticket') or 'Orchestration'} Ledger"


def main():
    ap = argparse.ArgumentParser(description="Render a roll-up JSON as the ledger HTML page.")
    ap.add_argument("rollup", nargs="?", help="roll-up JSON (default: newest in telemetry/rollup)")
    ap.add_argument("--out", help="HTML output path")
    a = ap.parse_args()
    src = Path(a.rollup) if a.rollup else max(ROLLUP_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime)
    data = slim(json.load(open(src, encoding="utf-8")))
    name = data["title"]
    html = TEMPLATE.read_text(encoding="utf-8")
    html = html.replace("__TITLE__", name).replace("__DATA__", json.dumps(data, default=str).replace("</", "<\\/"))
    out = Path(a.out or OUT_DIR / f"{src.stem}.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"{name} -> {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
