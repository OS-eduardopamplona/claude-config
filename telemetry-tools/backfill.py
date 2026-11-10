import argparse
import csv
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

PROJECTS = Path.home() / ".claude" / "projects"
OUT_DIR = Path.home() / ".claude" / "telemetry" / "backfill"

PRICES = [
    ("claude-fable-5-1", 10.0, 50.0, 0.25),
    ("claude-mythos-5-1", 10.0, 50.0, 0.25),
    ("claude-fable-5", 10.0, 50.0, 1.0),
    ("claude-mythos-5", 10.0, 50.0, 1.0),
    ("claude-opus-5-5", 4.0, 20.0, 0.20),
    ("claude-opus-5", 5.0, 25.0, None),
    ("claude-opus-4", 5.0, 25.0, None),
    ("claude-sonnet-5", 2.0, 10.0, 0.20),
    ("claude-sonnet-4", 3.0, 15.0, None),
    ("claude-haiku-5-5", 0.10, 0.50, None),
    ("claude-haiku-4", 1.0, 5.0, None),
]

TOKEN_FIELDS = ("input", "output", "thinking", "cache_read", "cache_write_5m", "cache_write_1h")
IDLE_CAP_S = 300


def price_of(model):
    for prefix, inp, out, read in PRICES:
        if model.startswith(prefix):
            return inp, out, read if read is not None else inp * 0.1
    return None


def cost_of(model, t):
    p = price_of(model)
    if p is None:
        return None
    inp, out, read = p
    return (
        t["input"] * inp
        + t["output"] * out
        + t["cache_read"] * read
        + t["cache_write_5m"] * inp * 1.25
        + t["cache_write_1h"] * inp * 2.0
    ) / 1_000_000


def session_of(path):
    rel = path.relative_to(PROJECTS).parts
    return rel[1] if len(rel) > 2 else Path(rel[1]).stem


def tokens_of(usage):
    cc = usage.get("cache_creation") or {}
    w5, w1 = cc.get("ephemeral_5m_input_tokens"), cc.get("ephemeral_1h_input_tokens")
    if w5 is None and w1 is None:
        w5, w1 = usage.get("cache_creation_input_tokens") or 0, 0
    return {
        "input": usage.get("input_tokens") or 0,
        "output": usage.get("output_tokens") or 0,
        "thinking": (usage.get("output_tokens_details") or {}).get("thinking_tokens") or 0,
        "cache_read": usage.get("cache_read_input_tokens") or 0,
        "cache_write_5m": w5 or 0,
        "cache_write_1h": w1 or 0,
    }


def transcripts(since, sessions):
    for path in PROJECTS.rglob("*.jsonl"):
        if since and datetime.fromtimestamp(path.stat().st_mtime, timezone.utc) < since:
            continue
        if sessions and session_of(path) not in sessions:
            continue
        yield path


def scan(since=None, sessions=None, until=None):
    messages = {}
    for path in transcripts(since, sessions):
        sid = session_of(path)
        subagent = "subagents" in path.parts
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if '"usage"' not in line or '"assistant"' not in line:
                    continue
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                m = d.get("message") or {}
                usage = m.get("usage")
                model = m.get("model") or ""
                if d.get("type") != "assistant" or not usage or model == "<synthetic>":
                    continue
                ts = d.get("timestamp")
                when = datetime.fromisoformat(ts.replace("Z", "+00:00")) if ts else None
                if when and ((since and when < since) or (until and when >= until)):
                    continue
                key = m.get("id") or d.get("requestId") or d.get("uuid")
                messages[(sid, key)] = (sid, model, subagent, when, tokens_of(usage), d)
    return messages.values()


def aggregate(messages):
    rows = {}
    for sid, model, subagent, when, t, d in messages:
        r = rows.setdefault(sid, {
            "session": sid, "cwd": d.get("cwd"), "branch": d.get("gitBranch"),
            "first": when, "last": when, "times": [], "requests": 0, "subagent_requests": 0,
            "cost_usd": 0.0, "unpriced_models": set(),
            "by_model": defaultdict(lambda: dict.fromkeys(TOKEN_FIELDS + ("requests", "cost_usd"), 0)),
            **dict.fromkeys(TOKEN_FIELDS, 0),
        })
        if when:
            r["times"].append(when)
            r["first"] = min(filter(None, (r["first"], when)))
            r["last"] = max(filter(None, (r["last"], when)))
        if d.get("gitBranch") and d.get("gitBranch") != "HEAD":
            r["branch"] = d["gitBranch"]
        r["requests"] += 1
        r["subagent_requests"] += subagent
        bm = r["by_model"][model]
        bm["requests"] += 1
        c = cost_of(model, t)
        if c is None:
            r["unpriced_models"].add(model)
        else:
            r["cost_usd"] += c
            bm["cost_usd"] += c
        for k in TOKEN_FIELDS:
            r[k] += t[k]
            bm[k] += t[k]
    for r in rows.values():
        r["by_model"] = {k: dict(v) for k, v in r["by_model"].items()}
        r["unpriced_models"] = sorted(r["unpriced_models"])
        times = sorted(r.pop("times"))
        gaps = (min((b - a).total_seconds(), IDLE_CAP_S) for a, b in zip(times, times[1:]))
        r["active_min"] = round(sum(gaps) / 60, 1)
        r["active_span_min"] = round((r["last"] - r["first"]).total_seconds() / 60, 1) if r["first"] else None
        r["first"] = r["first"].isoformat() if r["first"] else None
        r["last"] = r["last"].isoformat() if r["last"] else None
        r["cost_usd"] = round(r["cost_usd"], 4)
    return sorted(rows.values(), key=lambda r: r["first"] or "")


def parse_date(s):
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc) if s else None


def main():
    ap = argparse.ArgumentParser(description="Token and cost per Claude Code session from local transcripts.")
    ap.add_argument("--since", help="UTC date or datetime, e.g. 2026-11-09")
    ap.add_argument("--until", help="UTC date or datetime, exclusive")
    ap.add_argument("--session", action="append", help="CLI session id (repeatable)")
    ap.add_argument("--out", default=str(OUT_DIR / "sessions.json"))
    ap.add_argument("--csv", help="also write a flat CSV here")
    a = ap.parse_args()
    rows = aggregate(scan(parse_date(a.since), set(a.session or []) or None, parse_date(a.until)))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    if a.csv:
        cols = ["session", "branch", "first", "last", "requests", "subagent_requests", *TOKEN_FIELDS, "cost_usd"]
        with open(a.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
    total = sum(r["cost_usd"] for r in rows)
    print(f"{len(rows)} sessions, ${total:,.2f} estimated -> {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
