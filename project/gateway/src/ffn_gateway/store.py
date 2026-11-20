"""SQLite persistence: raw frames, events (the timeline), the dispatch outbox and a small key-value table.
Everything the dashboard shows is read back from here, so a restart of the application loses nothing."""
from __future__ import annotations

import json
import sqlite3
import threading
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS frames(id INTEGER PRIMARY KEY, t REAL, box INT, type INT, seq INT, rssi INT, snr INT, hex TEXT, flags INT);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, t REAL, kind TEXT, box INT, level INT, text TEXT, data TEXT);
CREATE TABLE IF NOT EXISTS outbox(id INTEGER PRIMARY KEY, t REAL, channel TEXT, target TEXT, payload TEXT, attempts INT DEFAULT 0, next_t REAL, done INT DEFAULT 0, error TEXT);
CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT);
CREATE INDEX IF NOT EXISTS ix_frames_box ON frames(box, t);
CREATE INDEX IF NOT EXISTS ix_events_t ON events(t);
"""


class Store:
    def __init__(self, path: str = ":memory:"):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.db.executescript(SCHEMA)
            self.db.commit()

    def _x(self, sql, args=()):
        with self.lock:
            cur = self.db.execute(sql, args)
            self.db.commit()
            return cur

    def _q(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.db.execute(sql, args).fetchall()]

    # frames
    def add_frame(self, t, box, type_, seq, rssi, snr, wire: bytes, flags=0):
        self._x("INSERT INTO frames(t,box,type,seq,rssi,snr,hex,flags) VALUES(?,?,?,?,?,?,?,?)", (t, box, type_, seq, rssi, snr, wire.hex(), flags))

    def frames(self, box=None, limit=100):
        if box is None:
            return self._q("SELECT * FROM frames ORDER BY id DESC LIMIT ?", (limit,))
        return self._q("SELECT * FROM frames WHERE box=? ORDER BY id DESC LIMIT ?", (box, limit))

    # events
    def add_event(self, kind, text, box=0, level=0, data=None, t=None):
        self._x("INSERT INTO events(t,kind,box,level,text,data) VALUES(?,?,?,?,?,?)",
                (time.time() if t is None else t, kind, box, level, text, json.dumps(data or {})))

    def events(self, limit=200, kind=None, since=None):
        q, a = "SELECT * FROM events", []
        w = []
        if kind:
            w.append("kind=?"); a.append(kind)
        if since is not None:
            w.append("t>=?"); a.append(since)
        if w:
            q += " WHERE " + " AND ".join(w)
        rows = self._q(q + " ORDER BY id DESC LIMIT ?", (*a, limit))
        for r in rows:
            r["data"] = json.loads(r["data"])
        return rows

    # outbox (webhook, email, ... : anything that must be retried)
    def outbox_add(self, channel, target, payload: dict, t=None):
        t = time.time() if t is None else t
        return self._x("INSERT INTO outbox(t,channel,target,payload,next_t) VALUES(?,?,?,?,?)", (t, channel, target, json.dumps(payload), t)).lastrowid

    def outbox_due(self, now, limit=20):
        rows = self._q("SELECT * FROM outbox WHERE done=0 AND next_t<=? ORDER BY id LIMIT ?", (now, limit))
        for r in rows:
            r["payload"] = json.loads(r["payload"])
        return rows

    def outbox_done(self, oid):
        self._x("UPDATE outbox SET done=1, error=NULL WHERE id=?", (oid,))

    def outbox_fail(self, oid, now, error, backoff_s):
        self._x("UPDATE outbox SET attempts=attempts+1, next_t=?, error=? WHERE id=?", (now + backoff_s, error[:200], oid))

    def outbox_pending(self):
        return self._q("SELECT id,channel,target,attempts,error FROM outbox WHERE done=0")

    # kv
    def kv_get(self, k, default=None):
        r = self._q("SELECT v FROM kv WHERE k=?", (k,))
        return json.loads(r[0]["v"]) if r else default

    def kv_set(self, k, v):
        self._x("INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, json.dumps(v)))
