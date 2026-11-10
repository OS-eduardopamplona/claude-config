import argparse
import ctypes
import ctypes.wintypes as wt
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path.home() / ".claude" / "telemetry"
PIDS = ROOT / "pids"
RETAIN_DAYS = 90
PID_RETAIN_DAYS = 30
DATED = re.compile(r"-(\d{4}-\d{2}-\d{2})\.jsonl$")
OUT = ROOT / "resources"
LOG = ROOT / "otel" / "receiver.log"
SAMPLE_S = 15
SAMPLES_PER_LINE = 4
INTERVAL_S = SAMPLE_S * SAMPLES_PER_LINE
FILETIME_EPOCH = 116444736000000000
REGISTRY_SLACK = 10_000_000
CREATE_NO_WINDOW = 0x08000000
RESUME = re.compile(r"--resume[= ]\"?([0-9a-fA-F-]{36})")
INDEX_FIELDS = re.compile(r'"(sessionId|cliSessionId|cwd)":("(?:[^"\\]|\\.)*")')

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
HANDLE = wt.HANDLE
U64 = ctypes.c_ulonglong
U64P = ctypes.POINTER(U64)


SELF_PID = os.getpid()


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wt.DWORD),
        ("cntUsage", wt.DWORD),
        ("th32ProcessID", wt.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wt.DWORD),
        ("cntThreads", wt.DWORD),
        ("th32ParentProcessID", wt.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wt.DWORD),
        ("szExeFile", ctypes.c_wchar * 260),
    ]


class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
    _fields_ = [
        ("cb", wt.DWORD),
        ("PageFaultCount", wt.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
        ("PrivateUsage", ctypes.c_size_t),
    ]


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", U64),
        ("WriteOperationCount", U64),
        ("OtherOperationCount", U64),
        ("ReadTransferCount", U64),
        ("WriteTransferCount", U64),
        ("OtherTransferCount", U64),
    ]


class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", wt.DWORD),
        ("dwMemoryLoad", wt.DWORD),
        ("ullTotalPhys", U64),
        ("ullAvailPhys", U64),
        ("ullTotalPageFile", U64),
        ("ullAvailPageFile", U64),
        ("ullTotalVirtual", U64),
        ("ullAvailVirtual", U64),
        ("ullAvailExtendedVirtual", U64),
    ]


def _bind(name, restype, *argtypes):
    f = getattr(k32, name)
    f.restype = restype
    f.argtypes = argtypes
    return f


CreateToolhelp32Snapshot = _bind("CreateToolhelp32Snapshot", HANDLE, wt.DWORD, wt.DWORD)
Process32FirstW = _bind("Process32FirstW", wt.BOOL, HANDLE, ctypes.POINTER(PROCESSENTRY32W))
Process32NextW = _bind("Process32NextW", wt.BOOL, HANDLE, ctypes.POINTER(PROCESSENTRY32W))
OpenProcess = _bind("OpenProcess", HANDLE, wt.DWORD, wt.BOOL, wt.DWORD)
CloseHandle = _bind("CloseHandle", wt.BOOL, HANDLE)
GetProcessTimes = _bind("GetProcessTimes", wt.BOOL, HANDLE, U64P, U64P, U64P, U64P)
GetThreadTimes = _bind("GetThreadTimes", wt.BOOL, HANDLE, U64P, U64P, U64P, U64P)
GetCurrentThread = _bind("GetCurrentThread", HANDLE)
K32GetProcessMemoryInfo = _bind(
    "K32GetProcessMemoryInfo", wt.BOOL, HANDLE, ctypes.POINTER(PROCESS_MEMORY_COUNTERS_EX), wt.DWORD
)
GetProcessIoCounters = _bind("GetProcessIoCounters", wt.BOOL, HANDLE, ctypes.POINTER(IO_COUNTERS))
GetSystemTimes = _bind("GetSystemTimes", wt.BOOL, U64P, U64P, U64P)
GlobalMemoryStatusEx = _bind("GlobalMemoryStatusEx", wt.BOOL, ctypes.POINTER(MEMORYSTATUSEX))
QueryFullProcessImageNameW = _bind(
    "QueryFullProcessImageNameW", wt.BOOL, HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)
)

INVALID_HANDLE = HANDLE(-1).value
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
TH32CS_SNAPPROCESS = 0x2
PROCESS_ENV_ACCESS = 0x0400 | 0x0010
ENV_MAX = 256 * 1024
CLAUDE_PID_VAR = re.compile(r"(?:^|\x00)CLAUDE_PID=(\d+)\x00")

ntdll = ctypes.WinDLL("ntdll")
NtQueryInformationProcess = ntdll.NtQueryInformationProcess
NtQueryInformationProcess.restype = ctypes.c_long
NtQueryInformationProcess.argtypes = [HANDLE, ctypes.c_int, ctypes.c_void_p, wt.ULONG, ctypes.POINTER(wt.ULONG)]
ReadProcessMemory = _bind(
    "ReadProcessMemory", wt.BOOL, HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)
)


def _read(h, address, size):
    buf = ctypes.create_string_buffer(size)
    done = ctypes.c_size_t()
    if not ReadProcessMemory(h, ctypes.c_void_p(address), buf, size, ctypes.byref(done)):
        return None
    return buf.raw[: done.value]


def env_claude_pid(pid):
    h = OpenProcess(PROCESS_ENV_ACCESS, False, pid)
    if not h:
        return None
    try:
        pbi = (ctypes.c_void_p * 6)()
        if NtQueryInformationProcess(h, 0, pbi, ctypes.sizeof(pbi), None) != 0 or not pbi[1]:
            return None
        raw = _read(h, pbi[1] + 0x20, 8)
        if not raw:
            return None
        params = int.from_bytes(raw, "little")
        raw = _read(h, params + 0x80, 8)
        size_raw = _read(h, params + 0x3F0, 8)
        if not raw or not size_raw:
            return None
        env_at = int.from_bytes(raw, "little")
        size = min(int.from_bytes(size_raw, "little"), ENV_MAX)
        if not env_at or size <= 0:
            return None
        env = _read(h, env_at, size)
        if not env:
            return None
        m = CLAUDE_PID_VAR.search(env.decode("utf-16-le", errors="replace"))
        return int(m.group(1)) if m else None
    finally:
        CloseHandle(h)


ORPHAN = object()
_last_logged = {}


def log(message, exc=False):
    key = message
    now = time.monotonic()
    if now - _last_logged.get(key, -1e9) < 3600:
        return
    _last_logged[key] = now
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        text = f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} resource_sampler: {message}\n"
        if exc:
            text += traceback.format_exc()
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(text)
    except OSError:
        pass


def filetime_now():
    return int(time.time() * 10_000_000) + FILETIME_EPOCH


def iso_to_filetime(value):
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None
    return int(dt.timestamp() * 10_000_000) + FILETIME_EPOCH


def thread_cpu_s():
    c, e, k, u = U64(), U64(), U64(), U64()
    GetThreadTimes(GetCurrentThread(), ctypes.byref(c), ctypes.byref(e), ctypes.byref(k), ctypes.byref(u))
    return (k.value + u.value) / 1e7


def is_desktop_image(path):
    p = path.lower()
    return "\\windowsapps\\claude_" in p or "\\anthropicclaude\\" in p


def sessions_dir_of(image):
    parts = Path(image).parents
    for parent in parts:
        if parent.name.lower() == "claude-code":
            return parent.parent / "claude-code-sessions"
    return None


class Proc:
    __slots__ = ("pid", "ppid", "exe", "ctime", "cpu", "ws", "priv", "rd", "wr")


class Sampler:
    def __init__(self):
        self.cores = os.cpu_count() or 1
        self.entry = PROCESSENTRY32W()
        self.mem = PROCESS_MEMORY_COUNTERS_EX()
        self.mem.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS_EX)
        self.io = IO_COUNTERS()
        self.ft = [U64() for _ in range(4)]
        self.buf = ctypes.create_unicode_buffer(1024)
        self.images = {}
        self.prev = {}
        self.prev_ft = None
        self.prev_sys = None
        self.sticky = {}
        self.env_cache = {}
        self.procs = {}
        self.parents = {}
        self.clis = {}
        self.cmdlines = {}
        self.pending = set()
        self.lookup_thread = None
        self.index = {}
        self.index_mtimes = {}
        self.index_scanned = 0.0
        self.sessions_dir = None
        self.lock = threading.Lock()
        self.overhead = []
        self.reset()

    def reset(self):
        self.n = 0
        self.cpu_pcts = []
        self.mem_used_max = 0
        self.commit_max = 0
        self.mem_total = 0
        self.sess = {}
        self.app = {"cpu": 0.0, "rss": 0}
        self.un = {"cpu": 0.0, "rss": 0, "top": Counter()}

    def snapshot(self):
        snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if snap == INVALID_HANDLE or not snap:
            raise OSError(ctypes.get_last_error(), "CreateToolhelp32Snapshot")
        entries = []
        e = self.entry
        e.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        try:
            ok = Process32FirstW(snap, ctypes.byref(e))
            while ok:
                entries.append((e.th32ProcessID, e.th32ParentProcessID, e.szExeFile))
                ok = Process32NextW(snap, ctypes.byref(e))
        finally:
            CloseHandle(snap)
        return entries

    def read_processes(self, entries):
        c, x, k, u = self.ft
        bc, bx, bk, bu = (ctypes.byref(v) for v in self.ft)
        mem, io = self.mem, self.io
        bmem, bio, memsize = ctypes.byref(mem), ctypes.byref(io), mem.cb
        procs = {}
        parents = {}
        for pid, ppid, exe in entries:
            parents[pid] = ppid
            if pid == 0:
                continue
            h = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not h:
                continue
            try:
                if not GetProcessTimes(h, bc, bx, bk, bu):
                    continue
                p = Proc()
                p.pid, p.ppid, p.exe, p.ctime = pid, ppid, exe, c.value
                p.cpu = k.value + u.value
                if K32GetProcessMemoryInfo(h, bmem, memsize):
                    p.ws, p.priv = mem.WorkingSetSize, mem.PrivateUsage
                else:
                    p.ws = p.priv = 0
                if GetProcessIoCounters(h, bio):
                    p.rd, p.wr = io.ReadTransferCount, io.WriteTransferCount
                else:
                    p.rd = p.wr = 0
                key = (pid, p.ctime)
                if exe.lower() == "claude.exe" and key not in self.images:
                    size = wt.DWORD(len(self.buf))
                    if QueryFullProcessImageNameW(h, 0, self.buf, ctypes.byref(size)):
                        self.images[key] = self.buf.value
                procs[pid] = p
            finally:
                CloseHandle(h)
        return procs, parents

    def load_registry(self, procs):
        valid = {}
        stale = []
        try:
            files = list(PIDS.glob("*.json"))
        except OSError:
            return valid, stale
        for f in files:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                pid = int(data["pid"])
            except (OSError, ValueError, KeyError, TypeError):
                try:
                    if time.time() - f.stat().st_mtime > 60:
                        stale.append(f)
                except OSError:
                    pass
                continue
            p = procs.get(pid)
            seen = iso_to_filetime(data.get("seen_at"))
            if p is None or seen is None or p.ctime > seen + REGISTRY_SLACK:
                stale.append(f)
                continue
            valid[pid] = data
        return valid, stale

    def classify_clis(self, procs, registry):
        desktop = set()
        candidates = []
        for pid, p in procs.items():
            image = self.images.get((pid, p.ctime))
            if image is None:
                continue
            if is_desktop_image(image):
                desktop.add(pid)
            else:
                candidates.append(p)
                if self.sessions_dir is None:
                    self.sessions_dir = sessions_dir_of(image)
        clis = {}
        for pid, data in registry.items():
            p = procs[pid]
            clis[pid] = {
                "key": (pid, p.ctime),
                "path": "registry",
                "cli_session": data.get("cli_session") or None,
                "host_session": data.get("host_session") or None,
                "cwd": data.get("cwd") or None,
            }
        for p in candidates:
            if p.pid in clis or p.ppid not in desktop:
                continue
            parent = procs[p.ppid]
            if parent.ctime > p.ctime:
                continue
            key = (p.pid, p.ctime)
            info = {"key": key, "path": "unmapped", "cli_session": None, "host_session": None, "cwd": None}
            with self.lock:
                cmd = self.cmdlines.get(key)
                if cmd is None:
                    self.pending.add(key)
            if cmd is not None:
                m = RESUME.search(cmd)
                if m:
                    uuid = m.group(1).lower()
                    info["path"] = "resume"
                    info["cli_session"] = uuid
                    host, cwd = self.index.get(uuid, (None, None))
                    info["host_session"], info["cwd"] = host, cwd
            clis[p.pid] = info
        return desktop, clis

    def owner_of(self, pid, procs, parents, desktop, clis, memo):
        chain = []
        result = "un"
        cur = pid
        seen = set()
        while True:
            if cur in memo:
                result = memo[cur]
                if result is ORPHAN:
                    return self.resolve_orphan_chain(chain, procs, clis, memo)
                break
            if cur in seen:
                break
            seen.add(cur)
            if cur == SELF_PID:
                break
            p = procs.get(cur)
            if p is not None:
                key = (cur, p.ctime)
                if cur in clis and clis[cur]["key"] == key:
                    result = ("s", key)
                    chain.append(cur)
                    break
                if cur in desktop:
                    result = "app"
                    chain.append(cur)
                    break
                stuck = self.sticky.get(key)
                if stuck is not None:
                    result = stuck
                    chain.append(cur)
                    break
            chain.append(cur)
            parent = parents.get(cur)
            if parent is None or parent == cur or parent == 0:
                break
            pp = procs.get(parent)
            if (p is not None and pp is not None and pp.ctime > p.ctime) or (pp is None and parent not in parents):
                return self.resolve_orphan_chain(chain, procs, clis, memo)
            cur = parent
        for c in chain:
            memo[c] = result
        return result

    def resolve_orphan_chain(self, chain, procs, clis, memo):
        result = ORPHAN
        for c in reversed(chain):
            p = procs.get(c)
            if result is ORPHAN and p is not None:
                found = self.owner_from_env(p, clis)
                if found != "un":
                    result = found
            memo[c] = result
        return "un" if result is ORPHAN else result

    def owner_from_env(self, p, clis):
        key = (p.pid, p.ctime)
        if key in self.env_cache:
            cli_pid = self.env_cache[key]
        else:
            try:
                cli_pid = env_claude_pid(p.pid)
            except Exception:
                cli_pid = None
            self.env_cache[key] = cli_pid
        info = clis.get(cli_pid)
        if info is None or info["key"][1] > p.ctime:
            return "un"
        return ("s", info["key"])

    def start_lookup(self):
        with self.lock:
            if self.lookup_thread and self.lookup_thread.is_alive():
                return
            unindexed = any(
                info["path"] == "resume" and info["cli_session"] not in self.index for info in self.clis.values()
            )
            if not self.pending and not (unindexed and time.monotonic() - self.index_scanned > 120):
                return
            keys = sorted(self.pending)
            self.pending.clear()
        t = threading.Thread(target=self.lookup, args=(keys,), name="resource-sampler-lookup", daemon=True)
        self.lookup_thread = t
        t.start()

    def lookup(self, keys):
        try:
            found = self.query_cmdlines([pid for pid, _ in keys]) if keys else {}
        except Exception:
            log("command line lookup failed", exc=True)
            found = {}
        uuids = set()
        with self.lock:
            for key in keys:
                cmd = found.get(key[0], "")
                self.cmdlines[key] = cmd
                m = RESUME.search(cmd)
                if m:
                    uuids.add(m.group(1).lower())
        if uuids - set(self.index) or any(
            info["path"] == "resume" and info["cli_session"] not in self.index for info in self.clis.values()
        ):
            try:
                self.scan_index()
            except Exception:
                log("session index scan failed", exc=True)

    def query_cmdlines(self, pids):
        if not pids:
            return {}
        flt = " OR ".join(f"ProcessId={pid}" for pid in pids)
        script = (
            f"Get-CimInstance Win32_Process -Filter '{flt}' | "
            "ForEach-Object { [string]$_.ProcessId + [char]9 + [string]$_.CommandLine }"
        )
        out = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            creationflags=CREATE_NO_WINDOW,
        ).stdout
        result = {}
        for line in out.splitlines():
            pid, _, cmd = line.partition("\t")
            if pid.strip().isdigit():
                result[int(pid)] = cmd
        return result

    def scan_index(self):
        self.index_scanned = time.monotonic()
        base = self.sessions_dir
        if base is None or not base.is_dir():
            return
        for f in base.glob("*/*/local_*.json"):
            try:
                mtime = f.stat().st_mtime
            except OSError:
                continue
            if self.index_mtimes.get(f) == mtime:
                continue
            self.index_mtimes[f] = mtime
            try:
                with open(f, "r", encoding="utf-8", errors="replace") as fh:
                    head = fh.read(16384)
            except OSError:
                continue
            fields = {}
            for name, literal in INDEX_FIELDS.findall(head):
                if name not in fields:
                    try:
                        fields[name] = json.loads(literal)
                    except ValueError:
                        pass
            cli = fields.get("cliSessionId")
            if cli:
                self.index[cli.lower()] = (fields.get("sessionId"), fields.get("cwd"))

    def system_times(self):
        i, k, u = U64(), U64(), U64()
        GetSystemTimes(ctypes.byref(i), ctypes.byref(k), ctypes.byref(u))
        return i.value, k.value, u.value

    def memory(self):
        m = MEMORYSTATUSEX()
        m.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        GlobalMemoryStatusEx(ctypes.byref(m))
        return m.ullTotalPhys, m.ullTotalPhys - m.ullAvailPhys, m.ullTotalPageFile - m.ullAvailPageFile

    def sample(self):
        cpu0, wall0 = thread_cpu_s(), time.perf_counter()
        now_ft = filetime_now()
        sys_t = self.system_times()
        entries = self.snapshot()
        procs, parents = self.read_processes(entries)
        registry, stale = self.load_registry(procs)
        desktop, clis = self.classify_clis(procs, registry)
        baseline = self.prev_ft is None
        if not baseline and self.prev_sys:
            di = sys_t[0] - self.prev_sys[0]
            dt = (sys_t[1] - self.prev_sys[1]) + (sys_t[2] - self.prev_sys[2])
            if dt > 0:
                self.cpu_pcts.append(max(0.0, min(100.0, 100.0 * (dt - di) / dt)))
        total, used, commit = self.memory()
        self.mem_total = total
        self.mem_used_max = max(self.mem_used_max, used)
        self.commit_max = max(self.commit_max, commit)
        memo = {}
        prev = self.prev
        cur = {}
        sticky = {}
        rss = Counter()
        priv = Counter()
        count = Counter()
        for pid, p in procs.items():
            key = (pid, p.ctime)
            owner = self.owner_of(pid, procs, parents, desktop, clis, memo)
            if isinstance(owner, tuple):
                sticky[key] = owner
            cur[key] = (p.cpu, p.rd, p.wr)
            if baseline:
                continue
            before = prev.get(key)
            if before is None:
                before = (0, 0, 0) if p.ctime >= self.prev_ft else (p.cpu, p.rd, p.wr)
            dcpu = max(0, p.cpu - before[0]) / 1e7
            drd = max(0, p.rd - before[1])
            dwr = max(0, p.wr - before[2])
            rss[owner] += p.ws
            priv[owner] += p.priv
            count[owner] += 1
            if owner == "app":
                self.app["cpu"] += dcpu
            elif owner == "un":
                self.un["cpu"] += dcpu
                if dcpu:
                    self.un["top"][p.exe] += dcpu
            else:
                s = self.sess.get(owner)
                if s is None:
                    s = self.sess[owner] = {"cpu": 0.0, "rss": 0, "priv": 0, "procs": 0, "rd": 0, "wr": 0, "top": Counter()}
                s["cpu"] += dcpu
                s["rd"] += drd
                s["wr"] += dwr
                if dcpu:
                    s["top"][p.exe] += dcpu
        if not baseline:
            for owner, value in rss.items():
                if owner == "app":
                    self.app["rss"] = max(self.app["rss"], value)
                elif owner == "un":
                    self.un["rss"] = max(self.un["rss"], value)
                else:
                    s = self.sess[owner]
                    s["rss"] = max(s["rss"], value)
                    s["priv"] = max(s["priv"], priv[owner])
                    s["procs"] = max(s["procs"], count[owner])
            self.n += 1
        self.sticky = sticky
        self.env_cache = {k: v for k, v in self.env_cache.items() if k in cur}
        self.prev = cur
        self.prev_ft = now_ft
        self.prev_sys = sys_t
        self.procs = procs
        self.clis = clis
        self.stale = stale
        self.start_lookup()
        self.overhead.append((thread_cpu_s() - cpu0, time.perf_counter() - wall0, len(procs)))
        del self.overhead[:-240]

    def build_line(self):
        mb = 1024 * 1024
        gb = 1024 ** 3
        try:
            disk = shutil.disk_usage("C:\\")
            disk_total, disk_free = disk.total / gb, disk.free / gb
        except OSError:
            disk_total = disk_free = 0.0
        sessions = []
        for info in self.clis.values():
            s = self.sess.get(("s", info["key"]))
            if s is None:
                s = {"cpu": 0.0, "rss": 0, "priv": 0, "procs": 0, "rd": 0, "wr": 0, "top": Counter()}
            sessions.append({
                "host_session": info["host_session"],
                "cli_session": info["cli_session"],
                "cli_pid": info["key"][0],
                "cwd": info["cwd"],
                "cpu_s": round(s["cpu"], 3),
                "rss_mb_max": round(s["rss"] / mb, 1),
                "private_mb_max": round(s["priv"] / mb, 1),
                "procs_max": s["procs"],
                "io_read_mb": round(s["rd"] / mb, 2),
                "io_write_mb": round(s["wr"] / mb, 2),
                "top": [[exe, round(v, 3)] for exe, v in s["top"].most_common(5)],
            })
        sessions.sort(key=lambda r: (-r["cpu_s"], r["cli_pid"]))
        pcts = self.cpu_pcts or [0.0]
        return {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "interval_s": INTERVAL_S,
            "machine": {
                "cores": self.cores,
                "cpu_pct_avg": round(sum(pcts) / len(pcts), 1),
                "cpu_pct_max": round(max(pcts), 1),
                "mem_total_gb": round(self.mem_total / gb, 2),
                "mem_used_gb_max": round(self.mem_used_max / gb, 2),
                "commit_gb_max": round(self.commit_max / gb, 2),
                "disk_total_gb": round(disk_total, 1),
                "disk_free_gb": round(disk_free, 1),
                "procs": len(self.procs),
            },
            "sessions": sessions,
            "app": {"cpu_s": round(self.app["cpu"], 3), "rss_mb_max": round(self.app["rss"] / mb, 1)},
            "unattributed": {
                "cpu_s": round(self.un["cpu"], 3),
                "rss_mb_max": round(self.un["rss"] / mb, 1),
                "top": [[exe, round(v, 3)] for exe, v in self.un["top"].most_common(8)],
            },
        }

    def flush(self):
        line = json.dumps(self.build_line(), separators=(",", ":"))
        self.reset()
        OUT.mkdir(parents=True, exist_ok=True)
        with open(OUT / f"samples-{datetime.now(timezone.utc):%Y-%m-%d}.jsonl", "a", encoding="utf-8") as f:
            f.write(line + "\n")
        for f in getattr(self, "stale", []):
            try:
                f.unlink()
            except OSError:
                pass
        return line


def prune(today):
    cutoff = (today - timedelta(days=RETAIN_DAYS)).isoformat()
    removed = 0
    for folder in (OUT, ROOT / "otel"):
        for f in folder.glob("*.jsonl"):
            m = DATED.search(f.name)
            if m and m.group(1) < cutoff:
                f.unlink(missing_ok=True)
                removed += 1
    stale = time.time() - PID_RETAIN_DAYS * 86400
    for f in PIDS.glob("*.json"):
        if f.stat().st_mtime < stale:
            f.unlink(missing_ok=True)
            removed += 1
    if removed:
        log(f"pruned {removed} files older than retention")


def run(stop_event, on_line=None, lines=None):
    sampler = Sampler()
    written = 0
    pruned_on = None
    try:
        sampler.sample()
    except Exception:
        log("baseline sample failed", exc=True)
    next_at = time.monotonic() + SAMPLE_S
    while not stop_event.wait(max(0.0, next_at - time.monotonic())):
        now = time.monotonic()
        next_at = next_at + SAMPLE_S if now - next_at < SAMPLE_S else now + SAMPLE_S
        try:
            sampler.sample()
        except Exception:
            log("sample failed", exc=True)
            continue
        if sampler.n < SAMPLES_PER_LINE:
            continue
        today = datetime.now(timezone.utc).date()
        if today != pruned_on:
            pruned_on = today
            try:
                prune(today)
            except Exception:
                log("prune failed", exc=True)
        try:
            line = sampler.flush()
        except Exception:
            log("write failed", exc=True)
            sampler.reset()
            continue
        written += 1
        if written == 1:
            o = sampler.overhead[1:] or sampler.overhead
            log(
                "running; per-sample cpu ms avg %.1f max %.1f, wall ms avg %.1f, procs %d"
                % (
                    1000 * sum(x[0] for x in o) / len(o),
                    1000 * max(x[0] for x in o),
                    1000 * sum(x[1] for x in o) / len(o),
                    o[-1][2],
                )
            )
        if on_line:
            on_line(line, sampler)
        if lines is not None and written >= lines:
            break
    return sampler


def start(stop_event):
    def guarded():
        try:
            run(stop_event)
        except Exception:
            log("sampler stopped", exc=True)

    t = threading.Thread(target=guarded, name="resource-sampler", daemon=True)
    t.start()
    return t


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--once", action="store_true")
    group.add_argument("--minutes", type=int)
    args = parser.parse_args()

    def show(line, sampler):
        print(line, flush=True)
        o = sampler.overhead[-SAMPLES_PER_LINE:]
        paths = Counter(info["path"] for info in sampler.clis.values())
        print(
            "overhead per 15 s sample: cpu ms %s, wall ms %s, procs %d; clis %s"
            % (
                [round(1000 * x[0], 1) for x in o],
                [round(1000 * x[1], 1) for x in o],
                o[-1][2],
                dict(paths),
            ),
            file=sys.stderr,
            flush=True,
        )

    run(threading.Event(), on_line=show, lines=1 if args.once else args.minutes)


if __name__ == "__main__":
    main()
