import argparse
import csv
import json
import os
import re
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

SHELL_TOOLS = {"Bash", "PowerShell"}
FILE_TOOLS = {"Read", "Edit", "Write", "MultiEdit", "Grep", "Glob", "NotebookEdit"}
SUBAGENT_TOOLS = {"Agent", "Task"}
TOOL_CATEGORIES = ("build", "test", "node", "git", "remote", "other_shell", "subagent", "mcp", "file", "other")
WORD = r"(?<![\w.\\/-])"
COMMAND_CATEGORIES = [
    ("test", re.compile(r"dotnet(\.exe)?\s+test\b|\b(npm|pnpm|yarn)\s+(run\s+)?test|\bvitest\b|\bplaywright\b|build\.ps1.*-target\s+tests?\b", re.I)),
    ("build", re.compile(r"dotnet(\.exe)?\s+(build|msbuild|pack|publish)\b|" + WORD + r"msbuild(\.exe)?\s|build\.ps1|\bcake\b", re.I)),
    ("node", re.compile(WORD + r"(npm|npx|pnpm|yarn|node)(\.exe|\.cmd)?\s", re.I)),
    ("remote", re.compile(WORD + r"(gh|az)(\.exe|\.cmd)?\s+[a-z]|" + WORD + r"(curl|wget)(\.exe)?\s|invoke-(webrequest|restmethod)", re.I)),
    ("git", re.compile(WORD + r"git(\.exe)?\s+-?[a-z]", re.I)),
]
NOTIFIED_TOOL = re.compile(r"<tool-use-id>(toolu_\w+)</tool-use-id>")
CLOUD_ID = re.compile(r"session_01[A-Za-z0-9]{20,}")
ABS_PATH = r"(?<![\w./\x5c])(?:[A-Za-z]:|/[a-zA-Z](?=/))[/\x5c]+[^\s\"'`;&|<>()*?]+"
WORKING_PATH = re.compile(r"(?:\bcd\s+|\bpushd\s+|\s-C\s+|\bworktree\s+add\s+(?:[^\s;&|]+\s+)*?)[\"']?(" + ABS_PATH + ")", re.I)
SHELL_FG_CAP_S = 610


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


def command_category(command):
    for category, rx in COMMAND_CATEGORIES:
        if rx.search(command):
            return category
    return "other_shell"


def tool_category(name, inp):
    if name in SHELL_TOOLS:
        return command_category(inp.get("command") or "")
    if name in SUBAGENT_TOOLS:
        return "subagent"
    if name.startswith("mcp__"):
        return "mcp"
    if name in FILE_TOOLS:
        return "file"
    return "other"


def parse_ts(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00")) if ts else None


def earliest(a, b):
    return b if a is None or (b is not None and b < a) else a


def scan_full(since=None, sessions=None, until=None):
    messages, tools, activity, mentions, paths = {}, defaultdict(dict), defaultdict(set), {}, defaultdict(set)

    def use_of(sid, tid):
        return tools[sid].setdefault(tid, {"name": None, "category": None, "command": None, "bg": False,
                                           "start": None, "result": None, "notified": None})

    for path in transcripts(since, sessions):
        sid = session_of(path)
        subagent = "subagents" in path.parts
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.startswith('{"type":"api-request'):
                    continue
                if '"user"' not in line and '"assistant"' not in line and "queue-operation" not in line:
                    continue
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                kind = d.get("type")
                try:
                    when = parse_ts(d.get("timestamp"))
                except ValueError:
                    continue
                if not when or (since and when < since) or (until and when >= until):
                    continue
                if kind == "queue-operation":
                    if d.get("operation") == "enqueue":
                        for tid in NOTIFIED_TOOL.findall(d.get("content") or ""):
                            u = use_of(sid, tid)
                            u["notified"] = earliest(u["notified"], when)
                    continue
                if kind not in ("user", "assistant"):
                    continue
                activity[sid].add(int(when.timestamp() // 60))
                if "session_01" in line:
                    for cloud in set(CLOUD_ID.findall(line)):
                        first, last = mentions.get(cloud, (when, when))
                        mentions[cloud] = (min(first, when), max(last, when))
                m = d.get("message") or {}
                content = m.get("content")
                if isinstance(content, list):
                    for x in content:
                        if not isinstance(x, dict):
                            continue
                        if x.get("type") == "tool_use" and x.get("id"):
                            inp = x.get("input") or {}
                            u = use_of(sid, x["id"])
                            u["name"] = x.get("name") or ""
                            u["category"] = tool_category(u["name"], inp)
                            u["command"] = str(inp.get("command") or "") if u["name"] in SHELL_TOOLS else None
                            u["bg"] = bool(inp.get("run_in_background"))
                            u["start"] = earliest(u["start"], when)
                            if u["command"]:
                                paths[sid].update(WORKING_PATH.findall(u["command"]))
                        elif x.get("type") == "tool_result" and x.get("tool_use_id"):
                            u = use_of(sid, x["tool_use_id"])
                            u["result"] = earliest(u["result"], when)
                usage = m.get("usage")
                model = m.get("model") or ""
                if kind != "assistant" or not usage or model == "<synthetic>":
                    continue
                key = m.get("id") or d.get("requestId") or d.get("uuid")
                messages[(sid, key)] = (sid, model, subagent, when, tokens_of(usage), d)
    return {"messages": list(messages.values()), "tools": tools, "activity": activity, "mentions": mentions,
            "paths": paths}


def scan(since=None, sessions=None, until=None):
    return scan_full(since, sessions, until)["messages"]


def empty_tool_time():
    return {
        "by_category": {c: {"seconds": 0.0, "calls": 0, "bg_seconds": 0.0, "bg_calls": 0, "unfinished": 0, "capped": 0}
                        for c in TOOL_CATEGORIES},
        "longest": None,
    }


def tool_time(uses):
    out = empty_tool_time()
    for u in uses.values():
        if not u["start"] or not u["category"]:
            continue
        c = out["by_category"][u["category"]]
        end = u["notified"] if u["bg"] else u["result"]
        c["bg_calls" if u["bg"] else "calls"] += 1
        if not end:
            c["unfinished"] += 1
            continue
        seconds = max((end - u["start"]).total_seconds(), 0.0)
        capped = u["command"] is not None and not u["bg"] and seconds > SHELL_FG_CAP_S
        if capped:
            seconds = SHELL_FG_CAP_S
            c["capped"] += 1
        c["bg_seconds" if u["bg"] else "seconds"] += seconds
        if u["command"] is not None and not capped and (out["longest"] is None or seconds > out["longest"]["seconds"]):
            out["longest"] = {"category": u["category"], "seconds": round(seconds, 1),
                              "command": " ".join(u["command"].split())[:80], "background": u["bg"]}
    return finish_tool_time(out)


def finish_tool_time(t):
    for c in t["by_category"].values():
        c["seconds"] = round(c["seconds"], 1)
        c["bg_seconds"] = round(c["bg_seconds"], 1)
    cats = t["by_category"].values()
    t["background"] = {"calls": sum(c["bg_calls"] for c in cats), "seconds": round(sum(c["bg_seconds"] for c in cats), 1)}
    t["unfinished"] = sum(c["unfinished"] for c in cats)
    t["capped"] = sum(c["capped"] for c in cats)
    return t


def merge_tool_time(items):
    out = empty_tool_time()
    for t in items:
        if not t:
            continue
        for cat, c in t["by_category"].items():
            for k, v in c.items():
                out["by_category"][cat][k] += v
        if t.get("longest") and (out["longest"] is None or t["longest"]["seconds"] > out["longest"]["seconds"]):
            out["longest"] = dict(t["longest"])
    return finish_tool_time(out)


def build_test_seconds(t):
    if not t:
        return 0.0
    return sum(t["by_category"][c]["seconds"] + t["by_category"][c]["bg_seconds"] for c in ("build", "test"))


def aggregate(messages, tools=None):
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
        if tools is not None:
            r["tool_time"] = tool_time(tools.get(r["session"], {}))
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
    found = scan_full(parse_date(a.since), set(a.session or []) or None, parse_date(a.until))
    rows = aggregate(found["messages"], found["tools"])
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
