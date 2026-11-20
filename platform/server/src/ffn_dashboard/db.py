"""SQLite persistence for the dashboard. One connection, one lock: the load is a handful of writes per minute."""
from __future__ import annotations

import json
import sqlite3
import threading
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS alerts(
  id INTEGER PRIMARY KEY, alert_id TEXT, level INT, box INT, reason TEXT, lat REAL, lon REAL, text TEXT,
  t REAL, received REAL, acked_at REAL, data TEXT);
CREATE INDEX IF NOT EXISTS ix_alerts_t ON alerts(t);
CREATE TABLE IF NOT EXISTS missions(id TEXT PRIMARY KEY, t REAL, received REAL, data TEXT);
CREATE TABLE IF NOT EXISTS emails(id INTEGER PRIMARY KEY, t REAL, recipient TEXT, subject TEXT, body TEXT, status TEXT, error TEXT, alert_id TEXT);
CREATE TABLE IF NOT EXISTS events(gw_id INTEGER PRIMARY KEY, t REAL, kind TEXT, box INT, level INT, text TEXT, data TEXT);
CREATE INDEX IF NOT EXISTS ix_events_t ON events(t);
CREATE TABLE IF NOT EXISTS series(id INTEGER PRIMARY KEY, box INT, t REAL, gas REAL, fwi REAL, danger INT, battery INT,
  rssi INT, snr REAL, temp REAL, rh REAL, wind REAL, rain REAL, state INT);
CREATE INDEX IF NOT EXISTS ix_series_box ON series(box, t);
CREATE TABLE IF NOT EXISTS commands(id INTEGER PRIMARY KEY, t REAL, name TEXT, body TEXT, status TEXT, result TEXT, done_t REAL);
CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT, t REAL);
"""


class Db:
    def __init__(self, path: str = ":memory:"):
        self.c = sqlite3.connect(path, check_same_thread=False)
        self.c.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.c.execute("PRAGMA journal_mode=WAL") if path != ":memory:" else None
            self.c.executescript(SCHEMA)
            self.c.commit()

    def x(self, sql, args=()):
        with self.lock:
            cur = self.c.execute(sql, args)
            self.c.commit()
            return cur

    def q(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.c.execute(sql, args).fetchall()]

    # ---------------- kv
    def kv_set(self, k, v):
        self.x("INSERT INTO kv(k,v,t) VALUES(?,?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v, t=excluded.t", (k, json.dumps(v), time.time()))

    def kv_get(self, k, default=None):
        r = self.q("SELECT v FROM kv WHERE k=?", (k,))
        return json.loads(r[0]["v"]) if r else default

    def kv_time(self, k) -> float:
        r = self.q("SELECT t FROM kv WHERE k=?", (k,))
        return r[0]["t"] if r else 0.0

    # ---------------- alerts
    def add_alert(self, p: dict, received: float) -> dict:
        cur = self.x("INSERT INTO alerts(alert_id,level,box,reason,lat,lon,text,t,received,data) VALUES(?,?,?,?,?,?,?,?,?,?)",
                     (p["alert_id"], p["level"], p.get("box", 0), p.get("reason", ""), p.get("lat", 0.0), p.get("lon", 0.0),
                      p.get("text", ""), p.get("t", received), received, json.dumps(p)))
        return self.alert(cur.lastrowid)

    def alert(self, rid):
        r = self.q("SELECT * FROM alerts WHERE id=?", (rid,))
        return _alert_row(r[0]) if r else None

    def alerts(self, limit=100, since=None):
        if since is not None:
            rows = self.q("SELECT * FROM alerts WHERE t>=? ORDER BY t DESC, id DESC LIMIT ?", (since, limit))
        else:
            rows = self.q("SELECT * FROM alerts ORDER BY t DESC, id DESC LIMIT ?", (limit,))
        return [_alert_row(r) for r in rows]

    def ack_alerts(self, alert_id: str | None, now: float) -> int:
        if alert_id:
            return self.x("UPDATE alerts SET acked_at=? WHERE alert_id=? AND acked_at IS NULL", (now, alert_id)).rowcount
        return self.x("UPDATE alerts SET acked_at=? WHERE level=3 AND acked_at IS NULL", (now,)).rowcount

    # ---------------- missions
    def add_mission(self, m: dict, received: float):
        self.x("INSERT INTO missions(id,t,received,data) VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data, received=excluded.received",
               (str(m["id"]), m.get("created", received), received, json.dumps(m)))

    def missions(self, limit=20):
        return [dict(json.loads(r["data"]), received=r["received"]) for r in self.q("SELECT * FROM missions ORDER BY t DESC LIMIT ?", (limit,))]

    # ---------------- emails
    def add_email(self, t, recipient, subject, body, status, error="", alert_id=""):
        return self.x("INSERT INTO emails(t,recipient,subject,body,status,error,alert_id) VALUES(?,?,?,?,?,?,?)",
                      (t, recipient, subject, body, status, error, alert_id)).lastrowid

    def emails(self, limit=50):
        return self.q("SELECT * FROM emails ORDER BY id DESC LIMIT ?", (limit,))

    # ---------------- gateway events (timeline mirror, keyed by the gateway's own id)
    def upsert_events(self, rows: list[dict]) -> list[dict]:
        new = []
        with self.lock:
            for e in rows:
                if "id" not in e:
                    continue
                cur = self.c.execute("INSERT OR IGNORE INTO events(gw_id,t,kind,box,level,text,data) VALUES(?,?,?,?,?,?,?)",
                                     (int(e["id"]), e.get("t", 0), e.get("kind", ""), e.get("box", 0), e.get("level", 0),
                                      e.get("text", ""), json.dumps(e.get("data") or {})))
                if cur.rowcount:
                    new.append(e)
            self.c.commit()
        return new

    def events(self, limit=200, kind=None, since=None):
        sql, a, w = "SELECT * FROM events", [], []
        if kind:
            w.append("kind=?"); a.append(kind)
        if since is not None:
            w.append("t>=?"); a.append(since)
        if w:
            sql += " WHERE " + " AND ".join(w)
        rows = self.q(sql + " ORDER BY t DESC, gw_id DESC LIMIT ?", (*a, limit))
        for r in rows:
            r["id"] = r.pop("gw_id")
            r["data"] = json.loads(r["data"] or "{}")
        return rows

    # ---------------- per-box time series
    def add_sample(self, box: int, t: float, s: dict, min_interval: float, keep: int) -> bool:
        last = self.q("SELECT t, state FROM series WHERE box=? ORDER BY t DESC LIMIT 1", (box,))
        if last and t - last[0]["t"] < min_interval and last[0]["state"] == s.get("state"):
            return False
        self.x("INSERT INTO series(box,t,gas,fwi,danger,battery,rssi,snr,temp,rh,wind,rain,state) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
               (box, t, s.get("gas"), s.get("fwi"), s.get("danger"), s.get("battery"), s.get("rssi"), s.get("snr"),
                s.get("temp"), s.get("rh"), s.get("wind"), s.get("rain"), s.get("state")))
        self.x("DELETE FROM series WHERE box=? AND id NOT IN (SELECT id FROM series WHERE box=? ORDER BY t DESC LIMIT ?)", (box, box, keep))
        return True

    def series(self, box: int, since: float = 0.0, limit: int = 2000):
        rows = self.q("SELECT * FROM series WHERE box=? AND t>=? ORDER BY t DESC LIMIT ?", (box, since, limit))
        rows.reverse()
        for r in rows:
            r.pop("id", None)
        return rows

    # ---------------- operator commands (queued for push mode, or logged after a direct call)
    def add_command(self, t, name, body: dict, status="queued", result=None) -> int:
        return self.x("INSERT INTO commands(t,name,body,status,result) VALUES(?,?,?,?,?)",
                      (t, name, json.dumps(body), status, json.dumps(result) if result is not None else None)).lastrowid

    def pending_commands(self):
        rows = self.q("SELECT * FROM commands WHERE status='queued' ORDER BY id")
        for r in rows:
            r["body"] = json.loads(r["body"])
        return rows

    def finish_command(self, cid, status, result, now):
        self.x("UPDATE commands SET status=?, result=?, done_t=? WHERE id=?", (status, json.dumps(result), now, cid))

    def commands(self, limit=50):
        rows = self.q("SELECT * FROM commands ORDER BY id DESC LIMIT ?", (limit,))
        for r in rows:
            r["body"] = json.loads(r["body"])
            r["result"] = json.loads(r["result"]) if r["result"] else None
        return rows


def _alert_row(r: dict) -> dict:
    d = json.loads(r.pop("data") or "{}")
    r["level_name"] = d.get("level_name", "")
    r["extra"] = {k: v for k, v in d.items() if k not in ("alert_id", "level", "level_name", "box", "reason", "lat", "lon", "text", "t")}
    r["acked"] = r["acked_at"] is not None
    return r
