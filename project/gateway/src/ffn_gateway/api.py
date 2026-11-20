"""HTTP API (standard library only) consumed by the dashboard (platform/) and by the vision service.
JSON in/out. If `api_token` is set, every request needs `Authorization: Bearer <token>` except GET /health."""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


def make_handler(gw):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, obj):
            b = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def _auth(self):
            tok = gw.cfg.api_token
            return not tok or self.headers.get("Authorization") == "Bearer " + tok

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}") if n else {}

        def do_GET(self):
            u = urlparse(self.path)
            q = parse_qs(u.query)
            now = time.time()
            if u.path == "/health":
                return self._send(200, {"ok": True, "t": now})
            if not self._auth():
                return self._send(401, {"error": "unauthorized"})
            if u.path == "/v1/status":
                return self._send(200, gw.snapshot(now))
            if u.path == "/v1/boxes":
                return self._send(200, [b.to_dict(now) for b in gw.reg.boxes.values()])
            if u.path == "/v1/alerts":
                return self._send(200, gw.alerts.last.to_dict())
            if u.path == "/v1/timeline":
                return self._send(200, gw.store.events(int(q.get("limit", ["200"])[0]), q.get("kind", [None])[0]))
            if u.path == "/v1/risk":
                return self._send(200, gw.slow.results)
            if u.path == "/v1/models":
                return self._send(200, gw.models.status)
            return self._send(404, {"error": "not found"})

        def do_POST(self):
            u = urlparse(self.path)
            if not self._auth():
                return self._send(401, {"error": "unauthorized"})
            try:
                body = self._body()
            except ValueError:
                return self._send(400, {"error": "bad json"})
            now = time.time()
            if u.path == "/v1/ack":
                return self._send(200, gw.run_command("ack", {}, now))
            if u.path == "/v1/camera-event":
                try:
                    gw.on_camera_event(int(body["box"]), str(body["label"]), float(body["conf"]), float(body.get("ms", 0)), now)
                except (KeyError, ValueError):
                    return self._send(400, {"error": "need box, label, conf"})
                return self._send(200, {"ok": True})
            route = {"/v1/sim/weather": "sim_weather", "/v1/test/sms": "test_sms"}
            if u.path in route or u.path == "/v1/cmd":
                name = route.get(u.path) or body.get("cmd")
                if u.path == "/v1/cmd" and name not in ("ping", "force_alert", "reset_fire", "thresholds"):
                    return self._send(400, {"error": "unknown cmd"})
                try:
                    return self._send(200, gw.run_command(name, body, now))
                except (KeyError, ValueError, TypeError):
                    return self._send(400, {"error": "need box" if name == "sim_weather" else "bad command"})
            return self._send(404, {"error": "not found"})

    return H


def serve(gw, background: bool = True):
    srv = ThreadingHTTPServer((gw.cfg.api_host, gw.cfg.api_port), make_handler(gw))
    if background:
        threading.Thread(target=srv.serve_forever, name="api", daemon=True).start()
    else:
        srv.serve_forever()
    return srv
