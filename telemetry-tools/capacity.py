import ctypes
import json
import math
import os
import re
import shutil
import subprocess
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOME = Path.home() / ".claude"
RESOURCES_DIR = HOME / "telemetry" / "resources"
DISK_CACHE = HOME / "telemetry" / "cache" / "disk.json"
DISK_TTL_S = 6 * 3600
BUCKET_S = 300
OS_RAM_GB = 4
DISK_HEADROOM = 1.2
ACTIVE_CPU_S = 1.0
HEAVY_DIRS = ("bin", "obj", "node_modules")
WORKTREE = re.compile(r"[\\/]\.claude[\\/]worktrees[\\/][^\\/]+", re.I)


def percentile(values, q):
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    return values[max(math.ceil(q / 100 * len(values)) - 1, 0)]


def median(values):
    return percentile(values, 50)


def rnd(v, n=2):
    return None if v is None else round(v, n)


def parse_iso(s):
    if not s:
        return None
    d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def load_samples(folder, lo, hi):
    samples = []
    folder = Path(folder or RESOURCES_DIR)
    for f in sorted(folder.glob("samples-*.jsonl")) if folder.is_dir() else []:
        with open(f, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                    ts = parse_iso(d.get("ts"))
                except (ValueError, TypeError):
                    continue
                if not ts or (lo and ts < lo) or (hi and ts >= hi):
                    continue
                d["_ts"] = ts
                d["_interval"] = float(d.get("interval_s") or 60)
                samples.append(d)
    samples.sort(key=lambda d: d["_ts"])
    return samples


def session_minutes(samples, local_ids, cli_to_local):
    by_local = defaultdict(dict)
    for i, s in enumerate(samples):
        for e in s.get("sessions") or []:
            host = e.get("host_session")
            owner = next((l for l in local_ids if host and (l == host or l.startswith(host) or host.startswith(l))), None)
            owner = owner or cli_to_local.get(e.get("cli_session"))
            if not owner:
                continue
            m = by_local[owner].setdefault(i, {"i": i, "interval": s["_interval"], "cpu_s": 0.0, "rss_mb": 0.0,
                                               "read_mb": 0.0, "write_mb": 0.0, "top": Counter()})
            add_entry(m, e)
    return by_local


def add_entry(m, e):
    m["cpu_s"] += float(e.get("cpu_s") or 0)
    m["rss_mb"] += float(e.get("rss_mb_max") or 0)
    m["read_mb"] += float(e.get("io_read_mb") or 0)
    m["write_mb"] += float(e.get("io_write_mb") or 0)
    for exe, cpu in e.get("top") or []:
        m["top"][exe] += float(cpu or 0)


def summarize_minutes(minute_maps):
    merged = {}
    for mm in minute_maps:
        for i, m in mm.items():
            t = merged.setdefault(i, {"interval": m["interval"], "cpu_s": 0.0, "rss_mb": 0.0, "read_mb": 0.0,
                                      "write_mb": 0.0, "top": Counter()})
            for k in ("cpu_s", "rss_mb", "read_mb", "write_mb"):
                t[k] += m[k]
            t["top"].update(m["top"])
    if not merged:
        return None
    cpu = sum(m["cpu_s"] for m in merged.values())
    seconds = sum(m["interval"] for m in merged.values())
    top = Counter()
    for m in merged.values():
        top.update(m["top"])
    return {
        "cpu_hours": rnd(cpu / 3600, 3), "avg_cores": rnd(cpu / seconds if seconds else None),
        "peak_rss_gb": rnd(max(m["rss_mb"] for m in merged.values()) / 1024),
        "io_read_gb": rnd(sum(m["read_mb"] for m in merged.values()) / 1024),
        "io_write_gb": rnd(sum(m["write_mb"] for m in merged.values()) / 1024),
        "sampled_min": rnd(seconds / 60, 1),
        "top": [[exe, round(c, 1)] for exe, c in top.most_common(5)],
    }


def machine_from_samples(samples):
    if not samples:
        return None
    last = samples[-1].get("machine") or {}
    cpu_avg, cpu_max, mem_used, hot = [], [], [], 0.0
    machine_cpu_s = sessions_cpu_s = app_cpu_s = unattributed_cpu_s = 0.0
    unattributed_top = Counter()
    footprint_cores, footprint_rss = [], []
    for s in samples:
        m = s.get("machine") or {}
        interval = s["_interval"]
        avg = m.get("cpu_pct_avg")
        if avg is not None:
            cpu_avg.append(float(avg))
            machine_cpu_s += float(avg) / 100 * float(m.get("cores") or 0) * interval
            if float(avg) >= 80:
                hot += interval / 60
        cpu_max.append(m.get("cpu_pct_max", avg))
        mem_used.append(m.get("mem_used_gb_max"))
        per_session = defaultdict(lambda: [0.0, 0.0])
        for e in s.get("sessions") or []:
            cpu = float(e.get("cpu_s") or 0)
            sessions_cpu_s += cpu
            key = e.get("host_session") or e.get("cli_session") or e.get("cli_pid")
            per_session[key][0] += cpu
            per_session[key][1] += float(e.get("rss_mb_max") or 0)
        for cpu, rss in per_session.values():
            if cpu >= ACTIVE_CPU_S:
                footprint_cores.append(cpu / interval)
                footprint_rss.append(rss / 1024)
        app_cpu_s += float((s.get("app") or {}).get("cpu_s") or 0)
        u = s.get("unattributed") or {}
        unattributed_cpu_s += float(u.get("cpu_s") or 0)
        for exe, cpu in u.get("top") or []:
            unattributed_top[exe] += float(cpu or 0)
    attributed = sessions_cpu_s + app_cpu_s + unattributed_cpu_s
    share = (lambda v: rnd(v / attributed, 3)) if attributed else (lambda v: None)
    return {
        "first_sample": samples[0]["_ts"].isoformat(), "last_sample": samples[-1]["_ts"].isoformat(),
        "sampled_min": rnd(sum(s["_interval"] for s in samples) / 60, 1),
        "cores": last.get("cores"), "mem_total_gb": rnd(last.get("mem_total_gb")),
        "peak_cpu_pct": rnd(max((v for v in cpu_max if v is not None), default=None), 1),
        "p95_cpu_pct": rnd(percentile(cpu_avg, 95), 1),
        "peak_ram_used_gb": rnd(max((v for v in mem_used if v is not None), default=None)),
        "minutes_cpu_ge_80": rnd(hot, 1),
        "cpu_hours": {"machine": rnd(machine_cpu_s / 3600, 3), "sessions": rnd(sessions_cpu_s / 3600, 3),
                      "app": rnd(app_cpu_s / 3600, 3), "unattributed": rnd(unattributed_cpu_s / 3600, 3)},
        "cpu_share": {"sessions": share(sessions_cpu_s), "app": share(app_cpu_s),
                      "unattributed": share(unattributed_cpu_s)},
        "unattributed_top": [[exe, round(c, 1)] for exe, c in unattributed_top.most_common(8)],
        "per_session_minute": {
            "active_minutes": len(footprint_cores),
            "avg_cores_median": rnd(median(footprint_cores)), "avg_cores_p95": rnd(percentile(footprint_cores, 95)),
            "peak_rss_gb_median": rnd(median(footprint_rss)), "peak_rss_gb_p95": rnd(percentile(footprint_rss, 95)),
        },
    }


def ram_gb():
    if os.name != "nt":
        return None

    class MemoryStatus(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

    status = MemoryStatus()
    status.dwLength = ctypes.sizeof(MemoryStatus)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return None
    return rnd(status.ullTotalPhys / 1024 ** 3, 1)


def cpu_model():
    reg = shutil.which("reg")
    if not reg:
        return None
    try:
        out = subprocess.run([reg, "query", r"HKLM\HARDWARE\DESCRIPTION\System\CentralProcessor\0", "/v",
                              "ProcessorNameString"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(r"ProcessorNameString\s+REG_SZ\s+(.+)", out.stdout)
    return m.group(1).strip() if m else None


def machine_spec():
    disk = shutil.disk_usage(Path.home().anchor)
    return {
        "cpu_model": cpu_model(), "logical_cores": os.cpu_count(), "ram_gb": ram_gb(),
        "disk_root": Path.home().anchor, "disk_total_gb": rnd(disk.total / 1024 ** 3, 1),
        "disk_free_gb": rnd(disk.free / 1024 ** 3, 1),
    }


def is_link(entry):
    try:
        return entry.is_symlink() or (hasattr(entry, "is_junction") and entry.is_junction())
    except OSError:
        return True


def dir_size(root):
    sizes = dict.fromkeys(("total",) + HEAVY_DIRS, 0)
    stack = [(root, None)]
    while stack:
        path, heavy = stack.pop()
        try:
            it = os.scandir(path)
        except OSError:
            continue
        with it:
            for e in it:
                if is_link(e):
                    continue
                try:
                    if e.is_dir(follow_symlinks=False):
                        stack.append((e.path, heavy or (e.name if e.name in HEAVY_DIRS else None)))
                    elif e.is_file(follow_symlinks=False):
                        n = e.stat(follow_symlinks=False).st_size
                        sizes["total"] += n
                        if heavy:
                            sizes[heavy] += n
                except OSError:
                    continue
    return {k: round(v / 1024 ** 3, 3) for k, v in sizes.items()}


def native_path(path):
    if not path:
        return None
    m = re.match(r"^/([a-zA-Z])(/|$)", path)
    if m:
        path = m.group(1).upper() + ":/" + path[m.end():]
    return os.path.normpath(path) if re.match(r"^[A-Za-z]:", path) else None


def worktree_of(path):
    path = native_path(path)
    m = WORKTREE.search(path or "")
    return path[:m.end()] if m else None


def worktree_roots(paths, known=None):
    known = {} if known is None else known
    roots = set()
    for raw in paths:
        path = native_path(raw)
        if not path:
            continue
        parts = Path(path).parts
        for depth in range(3, min(len(parts), 8) + 1):
            candidate = str(Path(*parts[:depth]))
            if candidate not in known:
                known[candidate] = os.path.isfile(os.path.join(candidate, ".git"))
            if known[candidate]:
                roots.add(candidate)
                break
    return roots


def disk_usage(paths):
    cache = {}
    if DISK_CACHE.exists():
        try:
            cache = json.load(open(DISK_CACHE, encoding="utf-8"))
        except (OSError, ValueError):
            cache = {}
    now = time.time()
    stale = [p for p in paths if os.path.isdir(p) and now - cache.get(p, {}).get("at", 0) > DISK_TTL_S]
    with ThreadPoolExecutor(8) as pool:
        for p, size in zip(stale, pool.map(dir_size, stale)):
            cache[p] = {"at": now, **size}
    DISK_CACHE.parent.mkdir(parents=True, exist_ok=True)
    DISK_CACHE.write_text(json.dumps(cache, indent=1), encoding="utf-8")
    return {p: ({k: v for k, v in cache[p].items() if k != "at"} if os.path.isdir(p) else None) for p in paths}


def disk_total(paths, sizes):
    present = [sizes[p] for p in set(paths) if sizes.get(p)]
    if not present:
        return None
    out = {k: round(sum(s[k] for s in present), 2) for k in ("total",) + HEAVY_DIRS}
    out["worktrees"] = len(present)
    out["gone"] = len(set(paths)) - len(present)
    out["heavy_share"] = rnd(sum(out[k] for k in HEAVY_DIRS) / out["total"], 3) if out["total"] else None
    return out


def concurrency(activity, cloud_spans, lo, hi):
    lo_s = int(lo.timestamp()) // BUCKET_S * BUCKET_S
    n = max(math.ceil((hi.timestamp() - lo_s) / BUCKET_S), 1)
    local, cloud = [0] * n, [0] * n
    for minutes in activity.values():
        for b in {(m * 60 - lo_s) // BUCKET_S for m in minutes}:
            if 0 <= b < n:
                local[b] += 1
    for first, last in cloud_spans.values():
        b0 = max(int((first.timestamp() - lo_s) // BUCKET_S), 0)
        b1 = min(int((last.timestamp() - lo_s) // BUCKET_S), n - 1)
        for b in range(b0, b1 + 1):
            cloud[b] += 1
    busy = [v for v in local if v]
    total = [a + b for a, b in zip(local, cloud)]
    return {
        "start": datetime.fromtimestamp(lo_s, timezone.utc).isoformat(), "bucket_min": BUCKET_S // 60,
        "local": local, "cloud": cloud,
        "peak_local": max(local), "p95_local": percentile(busy, 95), "median_local": median(busy),
        "busy_buckets": len(busy), "peak_cloud": max(cloud), "peak_total": max(total),
        "p95_total": percentile([v for v in total if v], 95),
    }


def sizing(conc, footprint, disk):
    p95 = (conc or {}).get("p95_local")
    cores = (footprint or {}).get("avg_cores_p95")
    rss = (footprint or {}).get("peak_rss_gb_p95")
    wt = (disk or {}).get("total")
    sampled = f"sampler, {(footprint or {}).get('active_minutes', 0)} busy session-minutes"
    inputs = {
        "p95_concurrent_local": {"value": p95, "measured": p95 is not None, "source": "transcripts"},
        "p95_avg_cores_per_session": {"value": cores, "measured": cores is not None, "source": sampled},
        "p95_peak_rss_gb_per_session": {"value": rss, "measured": rss is not None, "source": sampled},
        "worktrees_gb": {"value": wt, "measured": wt is not None, "source": "disk walk"},
    }
    return {
        "inputs": inputs,
        "cores_needed": rnd(p95 * cores, 1) if p95 is not None and cores is not None else None,
        "ram_needed_gb": rnd(p95 * rss + OS_RAM_GB, 1) if p95 is not None and rss is not None else None,
        "disk_needed_gb": rnd(wt * DISK_HEADROOM, 1) if wt is not None else None,
        "formulas": {
            "cores_needed": "p95 concurrent local sessions x p95 avg cores per session",
            "ram_needed_gb": f"p95 concurrent local sessions x p95 peak RSS per session + {OS_RAM_GB} GB OS",
            "disk_needed_gb": f"worktrees total x {DISK_HEADROOM}",
        },
    }


def window(since, activity):
    if since:
        return since
    firsts = [min(m) for m in activity.values() if m]
    return datetime.fromtimestamp(min(firsts) * 60, timezone.utc) if firsts else datetime.now(timezone.utc) - timedelta(days=1)


def first_sample_minute(folder=None):
    folder = Path(folder or RESOURCES_DIR)
    files = sorted(folder.glob("samples-*.jsonl")) if folder.is_dir() else []
    for f in files:
        with open(f, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    ts = parse_iso(json.loads(line).get("ts"))
                except (ValueError, TypeError):
                    continue
                if ts:
                    return int(ts.timestamp() // 60)
    return None
