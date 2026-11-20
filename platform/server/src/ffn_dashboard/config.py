"""Dashboard configuration: a JSON file, then environment variables (FFN_DASH_<FIELD>), then explicit overrides."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, fields
from pathlib import Path


@dataclass
class SmtpConfig:
    host: str = ""                 # "" = no SMTP: emails are recorded with status "logged"
    port: int = 587
    user: str = ""
    password: str = ""
    sender: str = "ffn-dashboard@localhost"
    starttls: bool = True


@dataclass
class DashboardConfig:
    host: str = "127.0.0.1"
    port: int = 3000
    db_path: str = "dashboard.db"
    # gateway link
    gateway_url: str = ""          # e.g. http://192.168.1.20:8090 ; "" = push mode only
    gateway_token: str = ""        # the gateway api_token
    poll_s: float = 5.0
    ingest_token: str = ""         # what the gateway sends as dashboard_token ("" = no check, demo only)
    operator_token: str = ""       # "" = operator actions open (demo); else required as Bearer on /api/ops/*
    push_offline_after_s: float = 60.0
    # site
    site_name: str = "Forest site"
    drone_base: dict = field(default_factory=lambda: {"lat": 0.0, "lon": 0.0})
    gateway_pos: dict = field(default_factory=lambda: {"lat": 0.0, "lon": 0.0})
    spare_gateway_pos: dict = field(default_factory=lambda: {"lat": 0.0, "lon": 0.0})
    # base maps offered in the UI. The default public OpenStreetMap servers are fine for a demo; for an operational
    # deployment use your own tile server or a provider, per the OSM tile usage policy.
    map_tiles: list = field(default_factory=lambda: [
        {"id": "osm", "name": "OpenStreetMap", "url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png", "max_zoom": 19,
         "attribution": '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'},
        {"id": "topo", "name": "Terrain (OpenTopoMap)", "url": "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png", "max_zoom": 17,
         "subdomains": "abc", "attribution": 'Map data &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, SRTM &middot; style &copy; <a href="https://opentopomap.org">OpenTopoMap</a> (CC-BY-SA)'},
    ])
    timezone: str = "Africa/Tunis"
    smtp: SmtpConfig = field(default_factory=SmtpConfig)
    web_dist: str = ""             # built web UI folder ("" = ../web/dist next to this package, if present)
    series_min_interval_s: float = 10.0
    series_keep: int = 5000        # samples kept per box


def _apply(obj, data: dict):
    for f in fields(obj):
        if f.name not in data:
            continue
        v = data[f.name]
        cur = getattr(obj, f.name)
        if isinstance(cur, SmtpConfig) and isinstance(v, dict):
            _apply(cur, v)
        else:
            setattr(obj, f.name, type(cur)(v) if isinstance(cur, (int, float, str, bool)) and not isinstance(cur, bool) else v)


def load_config(path: str | None = None, overrides: dict | None = None) -> DashboardConfig:
    cfg = DashboardConfig()
    if path:
        _apply(cfg, json.loads(Path(path).read_text(encoding="utf-8")))
    env = {}
    for f in fields(cfg):
        key = "FFN_DASH_" + f.name.upper()
        if key in os.environ and not isinstance(getattr(cfg, f.name), (dict, SmtpConfig)):
            raw = os.environ[key]
            cur = getattr(cfg, f.name)
            env[f.name] = raw.lower() in ("1", "true", "yes") if isinstance(cur, bool) else raw
    _apply(cfg, env)
    if overrides:
        _apply(cfg, overrides)
    return cfg
