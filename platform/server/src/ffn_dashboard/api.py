"""HTTP API of the dashboard (FastAPI). Three groups:
- /api/alerts, /api/missions, /api/email, /api/gateway/snapshot : written by the gateway (Bearer ingest_token);
- /api/overview, /api/timeline, ... and /api/stream (server-sent events): read by the web UI;
- /api/ops/* : operator actions (Bearer operator_token when one is configured)."""
from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .service import Service

COMMANDS = {"ping", "force_alert", "reset_fire", "thresholds"}


class AlertIn(BaseModel):
    alert_id: str
    level: int = Field(ge=0, le=5)
    level_name: str = ""
    box: int = 0
    reason: str = ""
    lat: float = 0.0
    lon: float = 0.0
    text: str = ""
    t: float | None = None
    model_config = {"extra": "allow"}


class MissionIn(BaseModel):
    id: str
    simulated: bool = True
    items: list[dict[str, Any]] = []
    target: dict[str, float] = {}
    base: dict[str, float] = {}
    model_config = {"extra": "allow"}


class EmailIn(BaseModel):
    to: str
    subject: str = ""
    body: str = ""
    model_config = {"extra": "allow"}


class SnapshotIn(BaseModel):
    status: dict[str, Any]
    timeline: list[dict[str, Any]] = []
    risk: dict[str, Any] | None = None
    models: dict[str, Any] | None = None


class AckIn(BaseModel):
    alert_id: str | None = None


class CommandIn(BaseModel):
    cmd: str
    box: int = Field(ge=1, le=15)
    smoke_on: float | None = None
    smoke_off: float | None = None
    camera: float | None = None


class WeatherIn(BaseModel):
    box: int = Field(ge=1, le=15)
    enable: bool = True
    wind_kmh: int = Field(10, ge=0, le=150)
    rain_mm: float = Field(0.0, ge=0, le=100)


class TestEmailIn(BaseModel):
    to: str


class TestSmsIn(BaseModel):
    text: str = "Test SMS from the forest fire network"


def _bearer(expected: str):
    def check(authorization: str | None = Header(default=None)):
        if expected and authorization != "Bearer " + expected:
            raise HTTPException(401, "unauthorized")
    return check


def create_app(svc: Service, start_link: bool = True) -> FastAPI:
    cfg = svc.cfg
    ingest = Depends(_bearer(cfg.ingest_token))
    operator = Depends(_bearer(cfg.operator_token))

    @asynccontextmanager
    async def lifespan(app):
        svc.hub.bind(asyncio.get_running_loop())
        if start_link:
            svc.start()
        yield
        svc.stop()

    app = FastAPI(title="Forest Fire Prevention Network: dashboard", version="1.0.0", lifespan=lifespan)

    # ---------------------------------------------------------------- health / config
    @app.get("/api/health")
    def health():
        return {"ok": True, "t": time.time(), "link": svc.link_view()}

    @app.get("/api/config")
    def config():
        return {"site": cfg.site_name, "drone_base": cfg.drone_base, "timezone": cfg.timezone,
                "operator_token_required": bool(cfg.operator_token), "smtp": svc.mailer.enabled,
                "link_mode": svc.link["mode"], "map_tiles": cfg.map_tiles}

    # ---------------------------------------------------------------- gateway ingest (push)
    @app.post("/api/alerts", dependencies=[ingest])
    def post_alert(a: AlertIn):
        return svc.ingest_alert(a.model_dump())

    @app.post("/api/missions", dependencies=[ingest])
    def post_mission(m: MissionIn):
        svc.ingest_mission(m.model_dump())
        return {"ok": True}

    @app.post("/api/email", dependencies=[ingest])
    def post_email(e: EmailIn):
        return svc.ingest_email(e.model_dump())

    @app.post("/api/gateway/snapshot", dependencies=[ingest])
    def post_snapshot(s: SnapshotIn):
        return svc.push_exchange(s.model_dump())

    # ---------------------------------------------------------------- reads for the UI
    @app.get("/api/overview")
    def overview():
        return svc.overview()

    @app.get("/api/alerts")
    def alerts(limit: int = Query(100, ge=1, le=1000), since: float | None = None):
        return svc.db.alerts(limit, since)

    @app.get("/api/timeline")
    def timeline(limit: int = Query(200, ge=1, le=2000), kind: str | None = None, since: float | None = None):
        return svc.db.events(limit, kind, since)

    @app.get("/api/boxes/{box}/series")
    def series(box: int, hours: float = Query(24, gt=0, le=24 * 30)):
        return svc.db.series(box, svc.clock() - hours * 3600)

    @app.get("/api/risk")
    def risk():
        return svc.risk_view()

    @app.get("/api/missions")
    def missions(limit: int = Query(20, ge=1, le=200)):
        return svc.db.missions(limit)

    @app.get("/api/emails")
    def emails(limit: int = Query(50, ge=1, le=500)):
        return svc.db.emails(limit)

    @app.get("/api/commands")
    def commands(limit: int = Query(50, ge=1, le=500)):
        return svc.db.commands(limit)

    @app.get("/api/stream")
    async def stream(request: Request):
        q = svc.hub.subscribe()

        async def gen():
            try:
                first = svc.overview()
                import json as _j
                yield f"event: overview\ndata: {_j.dumps(first, default=str)}\n\n"
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        seq, kind, data = await asyncio.wait_for(q.get(), timeout=15)
                        yield f"id: {seq}\nevent: {kind}\ndata: {data}\n\n"
                    except asyncio.TimeoutError:
                        yield ": keep-alive\n\n"
            finally:
                svc.hub.unsubscribe(q)

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # ---------------------------------------------------------------- operator actions
    @app.post("/api/ops/ack", dependencies=[operator])
    def ack(a: AckIn):
        return svc.command("ack", {"alert_id": a.alert_id} if a.alert_id else {})

    @app.post("/api/ops/command", dependencies=[operator])
    def command(c: CommandIn):
        if c.cmd not in COMMANDS:
            raise HTTPException(400, f"unknown command, use one of {sorted(COMMANDS)}")
        body = {"box": c.box}
        if c.cmd == "thresholds":
            if None in (c.smoke_on, c.smoke_off, c.camera):
                raise HTTPException(400, "thresholds need smoke_on, smoke_off and camera")
            if not (0 < c.smoke_off < c.smoke_on < 1 and 0 < c.camera < 1):
                raise HTTPException(400, "need 0 < smoke_off < smoke_on < 1 and 0 < camera < 1")
            body.update(smoke_on=c.smoke_on, smoke_off=c.smoke_off, camera=c.camera)
        return svc.command(c.cmd, body)

    @app.post("/api/ops/sim-weather", dependencies=[operator])
    def sim_weather(w: WeatherIn):
        return svc.command("sim_weather", w.model_dump())

    @app.post("/api/ops/test-sms", dependencies=[operator])
    def test_sms(s: TestSmsIn):
        return svc.command("test_sms", {"text": s.text})

    @app.post("/api/ops/test-email", dependencies=[operator])
    def test_email(e: TestEmailIn):
        return svc.send_test_email(e.to)

    # ---------------------------------------------------------------- web UI (built files), single-page fallback
    dist = Path(cfg.web_dist) if cfg.web_dist else Path(__file__).resolve().parents[3] / "web" / "dist"
    if (dist / "index.html").exists():
        if (dist / "assets").exists():
            app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith("api/"):
                raise HTTPException(404)
            f = dist / path
            if path and f.is_file() and dist in f.resolve().parents:
                return FileResponse(f)
            return FileResponse(dist / "index.html")

    return app
