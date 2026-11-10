import argparse
import json
import sys
from pathlib import Path

HOME = Path.home() / ".claude"
ROLLUP_DIR = HOME / "telemetry" / "rollup"
OUT_DIR = HOME / "telemetry" / "dashboard"
TEMPLATE = Path(__file__).with_name("dashboard.html")


def slim(rollup):
    tickets = []
    for t in rollup["tickets"]:
        tickets.append({
            "key": t["ticket"], "summary": t.get("summary"), "status": t.get("jira_status"),
            "category": t.get("jira_category"), "cycle": t.get("jira_cycle_days"),
            "sessions": t["sessions"], "cloud": t["cloud_sessions"], "requests": t["requests"],
            "tokens": t["tokens"], "cost": t["cost_usd"], "active": t["active_min"], "wall": t["wall_hours"],
            "ciRuns": t["ci_runs"], "ciMin": t["ci_minutes"], "ciReruns": t["ci_reruns"], "ciFailed": t["ci_failed"],
            "reviews": t["review_rounds"],
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
        "jiraFetchedAt": rollup.get("jira_fetched_at"), "gaps": rollup.get("gaps", []), "tickets": tickets,
    }


def main():
    ap = argparse.ArgumentParser(description="Render a roll-up JSON as the ledger HTML page.")
    ap.add_argument("rollup", nargs="?", help="roll-up JSON (default: newest in telemetry/rollup)")
    ap.add_argument("--out", help="HTML output path")
    a = ap.parse_args()
    src = Path(a.rollup) if a.rollup else max(ROLLUP_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime)
    data = slim(json.load(open(src, encoding="utf-8")))
    name = f"{data['rootTicket'] or 'Orchestration'} Ledger"
    html = TEMPLATE.read_text(encoding="utf-8")
    html = html.replace("__TITLE__", name).replace("__DATA__", json.dumps(data, default=str).replace("</", "<\\/"))
    out = Path(a.out or OUT_DIR / f"{src.stem}.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"{name} -> {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
