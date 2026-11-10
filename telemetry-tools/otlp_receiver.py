import gzip
import json
import os
import sys
import threading
import traceback
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT = int(os.environ.get("CLAUDE_OTLP_PORT", "14318"))
OUT = Path(os.environ.get("CLAUDE_OTLP_DIR", Path.home() / ".claude" / "telemetry" / "otel"))
SIGNALS = {"/v1/metrics": "metrics", "/v1/logs": "logs", "/v1/traces": "traces"}
LOCK = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        signal = SIGNALS.get(self.path.split("?")[0])
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if self.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
        if signal is None or "json" not in (self.headers.get("Content-Type") or ""):
            self.send_response(415 if signal else 404)
            self.end_headers()
            return
        try:
            payload = json.loads(body)
        except ValueError:
            self.send_response(400)
            self.end_headers()
            return
        now = datetime.now(timezone.utc)
        line = json.dumps({"received": now.isoformat(), "payload": payload}, separators=(",", ":"))
        OUT.mkdir(parents=True, exist_ok=True)
        with LOCK, open(OUT / f"{signal}-{now:%Y-%m-%d}.jsonl", "a", encoding="utf-8") as f:
            f.write(line + "\n")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b"{}")

    def do_GET(self):
        self.send_response(200 if self.path == "/health" else 404)
        self.end_headers()

    def log_message(self, *args):
        pass


def start_sampler():
    try:
        import resource_sampler

        resource_sampler.start(threading.Event())
    except Exception:
        try:
            OUT.mkdir(parents=True, exist_ok=True)
            with LOCK, open(OUT / "receiver.log", "a", encoding="utf-8") as f:
                f.write(f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} sampler failed to start\n")
                f.write(traceback.format_exc())
        except OSError:
            pass


if __name__ == "__main__":
    try:
        server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError as e:
        print(f"port {PORT} unavailable: {e}", file=sys.stderr)
        sys.exit(1)
    start_sampler()
    server.serve_forever()
