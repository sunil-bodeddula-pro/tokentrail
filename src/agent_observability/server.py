"""Local HTTP server: the dashboard page and a small JSON API.

    GET  /                 the dashboard
    GET  /api/telemetry    the latest snapshot (runs, commits, sync stats)
    POST /api/sync         re-scan now and return the new snapshot
    GET  /api/health       {"ok": true}

It binds to 127.0.0.1 by default: the data includes your prompts, so don't expose it on a network.
"""
from __future__ import annotations

import gzip
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .state import TelemetryState

STATIC = os.path.join(os.path.dirname(__file__), "static")


def make_handler(state: TelemetryState):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # quiet
            pass

        def _send(self, code: int, body: bytes, ctype: str):
            gz = "gzip" in self.headers.get("Accept-Encoding", "") and len(body) > 2048
            if gz:
                body = gzip.compress(body, 5)
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            if gz:
                self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code=200):
            self._send(code, json.dumps(obj).encode(), "application/json")

        def do_GET(self):
            path = self.path.split("?")[0]
            if path in ("/", "/index.html"):
                with open(os.path.join(STATIC, "dashboard.html"), "rb") as fh:
                    self._send(200, fh.read(), "text/html; charset=utf-8")
            elif path == "/api/telemetry":
                self._json(state.snapshot())
            elif path == "/api/health":
                self._json({"ok": True})
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self):
            if self.path.split("?")[0] == "/api/sync":
                self._json(state.sync())
            else:
                self._json({"error": "not found"}, 404)

    return Handler


def serve(state: TelemetryState, host: str, port: int):
    httpd = ThreadingHTTPServer((host, port), make_handler(state))
    print(f"Dashboard: http://{host}:{port}  (Ctrl+C to stop)", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
