"""Fan-out of an alert: dashboard webhook (outbox + retry), SMS through the bridge, email through the dashboard endpoint,
drone mission. The HTTP poster is a plain callable so tests replace it."""
from __future__ import annotations

import json
import time
import urllib.request

from . import drone as dronemod
from . import uart_link as U
from .alerts import NAMES


def http_post_json(url: str, body: dict, token: str = "", timeout: float = 5.0):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status


def http_exchange_json(url: str, body: dict, token: str = "", timeout: float = 5.0) -> dict:
    """POST JSON and return the decoded JSON answer (used by the dashboard uplink)."""
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


class Dispatcher:
    BACKOFF = (5, 15, 60, 300)

    def __init__(self, cfg, store, link=None, poster=http_post_json):
        self.cfg = cfg
        self.store = store
        self.link = link
        self.poster = poster
        self.sms_counter = 0
        self.sms_sent: dict[tuple, float] = {}

    def text_for(self, level: int, box: int, reason: str, lat: float, lon: float) -> str:
        where = f"{lat:.5f},{lon:.5f}" if lat or lon else "position unknown"
        if level == 3:
            return f"FIRE ALERT {('box ' + str(box)) if box else ''} {reason}. Near {where}. Check the dashboard."
        return f"{NAMES[level]}: box {box} {reason} ({where})"

    def notify(self, alert_id: str, level: int, box: int, reason: str, lat: float, lon: float, extra: dict | None = None,
               now=None, sms: bool = True):
        now = time.time() if now is None else now
        text = self.text_for(level, box, reason, lat, lon)
        payload = {"alert_id": alert_id, "level": level, "level_name": NAMES[level], "box": box, "reason": reason,
                   "lat": lat, "lon": lon, "text": text, "t": now, **(extra or {})}
        self.store.add_event("alert", text, box=box, level=level, data=payload, t=now)
        if self.cfg.dashboard_url:
            self.store.outbox_add("dashboard", self.cfg.dashboard_url.rstrip("/") + "/api/alerts", payload, t=now)
        if level == 3:
            if sms:
                self.sms(alert_id, box, text, now)
            for em in self.cfg.emails:
                self.store.outbox_add("email", em, {"subject": f"FIRE ALERT {alert_id}", "body": text, **payload}, t=now)
        return payload

    def sms(self, alert_id: str, box: int, text: str, now: float, force: bool = False):
        """One SMS per number per alert episode."""
        for number in self.cfg.phone_numbers:
            key = (alert_id, number)
            if key in self.sms_sent and not force:
                continue
            self.sms_sent[key] = now
            self.sms_counter = (self.sms_counter + 1) & 0x7FFF
            if self.link:
                self.link.send(U.send_sms(self.sms_counter, number, text))
            self.store.add_event("sms", f"SMS to {number}: {text[:80]}", box=box, level=3,
                                 data={"id": self.sms_counter, "number": number}, t=now)

    def drone(self, alert_id: str, lat: float, lon: float, now: float):
        if not self.cfg.drone.enabled:
            return None
        m = dronemod.build_mission(self.cfg, lat, lon, alert_id)
        res = dronemod.dispatch(self.cfg, m)
        self.store.add_event("drone", f"drone mission {alert_id} (simulated) -> {lat:.5f},{lon:.5f}", level=3,
                             data={"mission": m, **res}, t=now)
        if self.cfg.dashboard_url:
            self.store.outbox_add("dashboard", self.cfg.dashboard_url.rstrip("/") + "/api/missions", m, t=now)
        return m

    def flush(self, now=None) -> int:
        now = time.time() if now is None else now
        done = 0
        for row in self.store.outbox_due(now):
            try:
                if row["channel"] == "dashboard":
                    self.poster(row["target"], row["payload"], self.cfg.dashboard_token)
                elif row["channel"] == "email":
                    if not self.cfg.dashboard_url:
                        raise RuntimeError("no email transport: set dashboard_url (the dashboard backend sends the email)")
                    self.poster(self.cfg.dashboard_url.rstrip("/") + "/api/email", {"to": row["target"], **row["payload"]}, self.cfg.dashboard_token)
                else:
                    raise ValueError("unknown channel " + row["channel"])
                self.store.outbox_done(row["id"])
                done += 1
            except Exception as e:
                self.store.outbox_fail(row["id"], now, repr(e), self.BACKOFF[min(row["attempts"], len(self.BACKOFF) - 1)])
        return done
