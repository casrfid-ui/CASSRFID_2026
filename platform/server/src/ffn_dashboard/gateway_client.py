"""Small HTTP client for the gateway API (project/gateway, `ffn_gateway.api`). Standard library only."""
from __future__ import annotations

import json
import urllib.error
import urllib.request


class GatewayError(RuntimeError):
    pass


class GatewayClient:
    def __init__(self, base_url: str, token: str = "", timeout: float = 4.0):
        self.base = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _call(self, method: str, path: str, body: dict | None = None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method, headers={"Accept": "application/json"})
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if self.token:
            req.add_header("Authorization", "Bearer " + self.token)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            raise GatewayError(f"{method} {path}: HTTP {e.code}") from e
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            raise GatewayError(f"{method} {path}: {e}") from e

    # reads
    def status(self):
        return self._call("GET", "/v1/status")

    def timeline(self, limit: int = 200):
        return self._call("GET", f"/v1/timeline?limit={int(limit)}")

    def risk(self):
        return self._call("GET", "/v1/risk")

    def models(self):
        return self._call("GET", "/v1/models")

    # operator actions
    def run(self, name: str, body: dict):
        """Execute one operator command on the gateway. Names match the dashboard command queue."""
        if name == "ack":
            return self._call("POST", "/v1/ack", {})
        if name in ("ping", "force_alert", "reset_fire", "thresholds"):
            return self._call("POST", "/v1/cmd", {"cmd": name, **body})
        if name == "sim_weather":
            return self._call("POST", "/v1/sim/weather", body)
        if name == "test_sms":
            return self._call("POST", "/v1/test/sms", body)
        raise GatewayError("unknown command " + name)
