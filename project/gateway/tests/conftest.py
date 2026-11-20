import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "src"))
sys.path.insert(0, str(HERE.parent / "protocol" / "python"))

import pytest

from ffn_gateway.config import load_config
from ffn_gateway.app import Gateway
from ffn_gateway import uart_link as U


@pytest.fixture
def cfg(tmp_path):
    return load_config(None, {"db_path": ":memory:", "phone_numbers": ["+21600000001", "+21600000002"],
                              "emails": ["ops@example.org"], "dashboard_url": "http://dash.invalid",
                              "boxes": [{"id": 1, "name": "box-1", "lat": 36.80, "lon": 10.10}, {"id": 2, "name": "box-2", "lat": 36.81, "lon": 10.11}],
                              "drone": {"enabled": True, "base_lat": 36.79, "base_lon": 10.09, "missions_dir": str(tmp_path / "missions")}})


@pytest.fixture
def gw(cfg):
    link = U.Link(U.MemoryLink())
    posts = []
    g = Gateway(cfg, link, poster=lambda url, body, tok="": posts.append((url, body)))
    g.posts = posts
    return g
