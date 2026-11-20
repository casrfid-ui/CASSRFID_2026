"""Dashboard core: gateway link (pull and push), ingest, operator commands and the live event hub.

Two ways to reach the gateway, both supported at once:
- pull: the dashboard polls the gateway HTTP API (same LAN, demo bench);
- push: the gateway posts its snapshot to `/api/gateway/snapshot` and receives the queued operator commands in the response
  (works behind the mobile operator's NAT, the normal case with a 2G/LTE-M modem).
Alerts, missions and emails always arrive by push from the gateway dispatcher (its outbox retries until we answer 200)."""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time

from . import views
from .db import Db
from .gateway_client import GatewayClient, GatewayError
from .mailer import Mailer

log = logging.getLogger("ffn_dashboard")


class Hub:
    """Fan-out of server-sent events to every connected browser. `publish` is safe from any thread."""

    def __init__(self):
        self.loop: asyncio.AbstractEventLoop | None = None
        self.subs: set[asyncio.Queue] = set()
        self.seq = 0
        self.lock = threading.Lock()

    def bind(self, loop):
        self.loop = loop

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self.subs.add(q)
        return q

    def unsubscribe(self, q):
        self.subs.discard(q)

    def publish(self, kind: str, data):
        with self.lock:
            self.seq += 1
            msg = (self.seq, kind, json.dumps(data, default=str))
        if not self.loop:
            return
        for q in list(self.subs):
            self.loop.call_soon_threadsafe(self._put, q, msg)

    @staticmethod
    def _put(q, msg):
        if q.full():
            try:
                q.get_nowait()
            except asyncio.QueueEmpty:
                pass
        q.put_nowait(msg)


class Service:
    def __init__(self, cfg, db: Db | None = None, client: GatewayClient | None = None, clock=time.time):
        self.cfg = cfg
        self.db = db or Db(cfg.db_path)
        self.client = client if client is not None else (GatewayClient(cfg.gateway_url, cfg.gateway_token) if cfg.gateway_url else None)
        self.hub = Hub()
        self.mailer = Mailer(cfg.smtp)
        self.clock = clock
        self.link = {"mode": "pull" if self.client else "push", "online": False, "last_ok": 0.0, "last_push": 0.0,
                     "error": "", "polls": 0, "failures": 0}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.lock = threading.RLock()

    # ------------------------------------------------------------------ gateway snapshot (pull or push)
    def ingest_snapshot(self, status: dict, timeline: list | None = None, risk: dict | None = None, models: dict | None = None,
                        source: str = "pull"):
        now = self.clock()
        with self.lock:
            self.db.kv_set("status", status)
            if risk is not None:
                self.db.kv_set("risk", risk)
            if models is not None:
                self.db.kv_set("models", models)
            new_events = self.db.upsert_events(timeline or [])
            self.link.update(online=True, last_ok=now, error="")
            if source == "push":
                self.link["last_push"] = now
            ov = self.overview()
            for b in ov["boxes"]:
                if b.get("has_status"):
                    self.db.add_sample(b["id"], now, views.sample_of(b), self.cfg.series_min_interval_s, self.cfg.series_keep)
        for e in sorted(new_events, key=lambda e: e.get("id", 0)):
            self.hub.publish("event", e)
        self.hub.publish("overview", ov)
        return ov

    def poll_once(self) -> bool:
        if not self.client:
            return False
        self.link["polls"] += 1
        try:
            status = self.client.status()
            timeline = self.client.timeline(200)
            risk = self.client.risk()
            models = self.client.models()
        except GatewayError as e:
            self._link_down(str(e))
            return False
        self.ingest_snapshot(status, timeline, risk, models, "pull")
        return True

    def _link_down(self, err: str):
        was = self.link["online"]
        self.link.update(online=False, error=err)
        self.link["failures"] += 1
        if was:
            log.warning("gateway link lost: %s", err)
        self.hub.publish("overview", self.overview())

    def check_push_staleness(self):
        if self.client:
            return
        if self.link["online"] and self.clock() - self.link["last_push"] > self.cfg.push_offline_after_s:
            self._link_down(f"no snapshot pushed for {int(self.clock() - self.link['last_push'])} s")

    def start(self):
        if self._thread:
            return
        self._thread = threading.Thread(target=self._run, name="gateway-link", daemon=True)
        self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            try:
                if self.client:
                    self.poll_once()
                    self._flush_commands()
                else:
                    self.check_push_staleness()
            except Exception:                      # the link thread must survive anything
                log.exception("link loop error")
            self._stop.wait(self.cfg.poll_s)

    def stop(self):
        self._stop.set()

    # ------------------------------------------------------------------ push ingest from the gateway dispatcher
    def ingest_alert(self, p: dict) -> dict:
        row = self.db.add_alert(p, self.clock())
        self.hub.publish("alert", row)
        return row

    def ingest_mission(self, m: dict):
        self.db.add_mission(m, self.clock())
        self.hub.publish("mission", m)

    def ingest_email(self, body: dict) -> dict:
        to = str(body.get("to", ""))
        subject = str(body.get("subject") or f"Forest fire network: {body.get('level_name', 'alert')}")
        text = str(body.get("body") or body.get("text") or "")
        status, err = self.mailer.send(to, subject, text) if to else ("failed", "no recipient")
        rid = self.db.add_email(self.clock(), to, subject, text, status, err, str(body.get("alert_id", "")))
        e = {"id": rid, "to": to, "subject": subject, "status": status, "error": err}
        self.hub.publish("email", e)
        return e

    def push_exchange(self, body: dict) -> dict:
        """Gateway uplink: store the snapshot, answer with the queued operator commands (marked as sent)."""
        self.ingest_snapshot(body.get("status") or {}, body.get("timeline") or [], body.get("risk"), body.get("models"), "push")
        out = []
        for c in self.db.pending_commands():
            out.append({"id": c["id"], "name": c["name"], "body": c["body"]})
            self.db.finish_command(c["id"], "sent", {"via": "push"}, self.clock())
        return {"ok": True, "commands": out, "t": self.clock()}

    # ------------------------------------------------------------------ operator actions
    def command(self, name: str, body: dict | None = None) -> dict:
        body = body or {}
        now = self.clock()
        if name == "ack":
            self.db.ack_alerts(body.get("alert_id"), now)
        if self.client:
            try:
                res = self.client.run(name, body)
                cid = self.db.add_command(now, name, body, "done", res)
                out = {"id": cid, "name": name, "status": "done", "result": res}
            except GatewayError as e:
                cid = self.db.add_command(now, name, body, "queued", {"error": str(e)})
                out = {"id": cid, "name": name, "status": "queued", "error": str(e)}
        else:
            cid = self.db.add_command(now, name, body, "queued")
            out = {"id": cid, "name": name, "status": "queued", "note": "delivered with the gateway's next snapshot"}
        self.hub.publish("command", out)
        if self.client and out["status"] == "done":
            threading.Thread(target=self.poll_once, daemon=True).start()   # show the effect at once
        return out

    def _flush_commands(self):
        for c in self.db.pending_commands():
            try:
                res = self.client.run(c["name"], c["body"])
                self.db.finish_command(c["id"], "done", res, self.clock())
            except GatewayError:
                return

    def send_test_email(self, to: str) -> dict:
        return self.ingest_email({"to": to, "subject": "Forest fire network: test email",
                                  "body": "Test email from the forest fire network dashboard."})

    # ------------------------------------------------------------------ views
    def link_view(self) -> dict:
        now = self.clock()
        last = self.link["last_ok"]
        return {**self.link, "age_s": round(now - last, 1) if last else None, "gateway_url": self.cfg.gateway_url or None}

    def overview(self) -> dict:
        now = self.clock()
        st = self.db.kv_get("status", {}) or {}
        a = st.get("assessment") or {"top": 0, "top_name": "none", "alerts": [], "fire_boxes": []}
        per_box: dict[int, list[int]] = {}
        for x in a.get("alerts", []):
            per_box.setdefault(x.get("box", 0), []).append(x["level"])
        sys_levels = per_box.get(0, [])
        boxes = [views.box_view(b, per_box.get(b["id"], []) + sys_levels) for b in st.get("boxes", [])]
        boxes.sort(key=lambda b: b["id"])
        risk = self.db.kv_get("risk", {}) or {}
        fire = risk.get("fire") or {}
        dangers = [b["fwi"] for b in boxes if b.get("fwi") and b["fwi"].get("value") is not None]
        worst = max(dangers, key=lambda f: (f["danger"] or 0, f["value"] or 0)) if dangers else None
        missions = self.db.missions(1)
        unacked = [r for r in self.db.alerts(20) if r["level"] == 3 and not r["acked"]]
        alerts = sorted(a.get("alerts", []), key=lambda x: (-{3: 5, 4: 4, 2: 3, 5: 2, 1: 1}.get(x["level"], 0), x.get("box", 0)))
        return {
            "t": now, "site": {"name": self.cfg.site_name, "drone_base": self.cfg.drone_base, "gateway_pos": self.cfg.gateway_pos,
                     "spare_gateway_pos": self.cfg.spare_gateway_pos,
                     "timezone": self.cfg.timezone},
            "link": self.link_view(),
            "gateway": {"id": st.get("gateway_id"), "snapshot_t": st.get("t"), "bridge": st.get("bridge"), "stats": st.get("stats", {}),
                        "episode": st.get("episode"), "outbox_pending": st.get("outbox_pending", 0), "uplink": st.get("uplink")},
            "level": {"top": a.get("top", 0), "name": views.LEVEL_NAMES.get(a.get("top", 0), "none")},
            "alerts": alerts, "fire_boxes": a.get("fire_boxes", []), "fusion": st.get("fusion"),
            "boxes": boxes, "counts": {"boxes": len(boxes), "online": sum(1 for b in boxes if b["online"])},
            "fwi_worst": worst, "fire": fire, "mission": missions[0] if missions else None,
            "unacked_fire": unacked[0] if unacked else None,
            "mail": {"smtp": self.mailer.enabled},
            "comms": self._comms(),
        }

    def _comms(self) -> dict:
        sms = self.db.q("SELECT COUNT(*) n, MAX(t) last FROM events WHERE kind='sms'")[0]
        em = self.db.q("SELECT COUNT(*) n, MAX(t) last FROM emails")[0]
        last_status = self.db.q("SELECT status FROM emails ORDER BY id DESC LIMIT 1")
        return {"sms": sms["n"], "sms_last": sms["last"], "emails": em["n"], "emails_last": em["last"],
                "email_status": last_status[0]["status"] if last_status else None,
                "missions": self.db.q("SELECT COUNT(*) n FROM missions")[0]["n"]}

    def risk_view(self) -> dict:
        r = self.db.kv_get("risk", {}) or {}
        return {"fwi_forecast": r.get("fwi_forecast", {}), "risk": r.get("risk", {}), "trend": r.get("trend", {}),
                "fire": r.get("fire", {}), "errors": r.get("errors", {}), "updated": self.db.kv_time("risk"),
                "models": self.db.kv_get("models", {})}
