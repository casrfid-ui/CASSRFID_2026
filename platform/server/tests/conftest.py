import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "src"))

from fastapi.testclient import TestClient            # noqa: E402

from ffn_dashboard.api import create_app             # noqa: E402
from ffn_dashboard.config import load_config         # noqa: E402
from ffn_dashboard.service import Service            # noqa: E402

INGEST = {"Authorization": "Bearer ingest-secret"}


class FakeClient:
    """Stands in for the gateway API."""

    def __init__(self):
        self.calls, self.fail = [], False
        self.state = {"t": 1.0, "gateway_id": 8, "assessment": {"top": 0, "top_name": "none", "alerts": [], "fire_boxes": []},
                      "boxes": [], "stats": {"rx": 0}, "episode": None, "outbox_pending": 0}

    def _maybe_fail(self):
        from ffn_dashboard.gateway_client import GatewayError
        if self.fail:
            raise GatewayError("down")

    def status(self):
        self._maybe_fail(); return self.state

    def timeline(self, limit=200):
        self._maybe_fail(); return [{"id": 1, "t": 1.0, "kind": "alert", "box": 1, "level": 2, "text": "suspicion", "data": {}}]

    def risk(self):
        return {"fwi_forecast": {}, "fire": {}}

    def models(self):
        return {"fwi_forecast": "loaded"}

    def run(self, name, body):
        self._maybe_fail(); self.calls.append((name, body)); return {"ok": True}


@pytest.fixture
def make():
    def _make(client=None, **over):
        cfg = load_config(None, {"db_path": ":memory:", "ingest_token": "ingest-secret", **over})
        svc = Service(cfg, client=client)
        return svc, TestClient(create_app(svc, start_link=False))
    return _make
