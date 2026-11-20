"""Event memory of the gateway: what every box sent, what the model said, simple counters.

Kept in memory (last `keep` events) and, when a store folder is given, appended to <store>/log.jsonl, so a restart
reloads the recent history. Thread safe."""
import json
import threading
import time
from collections import deque
from pathlib import Path

ALERTS = ("fire", "smoke")


def percentile(values, q):
    v = sorted(values)
    return v[min(len(v) - 1, int(round(q * (len(v) - 1))))] if v else None


class EventLog:
    def __init__(self, store=None, keep=500):
        self.store = Path(store) if store else None
        self.events = deque(maxlen=keep)
        self.lock = threading.RLock()
        self.started = time.time()
        self.counts = {"fire": 0, "smoke": 0, "background": 0, "error": 0}
        self.ms = deque(maxlen=500)
        self.webhook = {"sent": 0, "failed": 0}
        if self.store and (self.store / "log.jsonl").exists():
            for line in (self.store / "log.jsonl").read_text().splitlines()[-keep:]:
                try:
                    self.events.append(json.loads(line))
                except ValueError:
                    pass

    def add(self, rec):
        with self.lock:
            self.events.append(rec)
            self.counts[rec["label"] if rec["label"] else "error"] += 1
            if rec.get("ms") is not None:
                self.ms.append(rec["ms"])
            if self.store:
                with open(self.store / "log.jsonl", "a") as f:
                    f.write(json.dumps(rec) + "\n")

    def recent(self, limit=50, label=None, box=None):
        with self.lock:
            out = [e for e in reversed(self.events)
                   if (label is None or e.get("label") == label) and (box is None or e.get("box") == box)]
        return out[:limit]

    def find(self, file):
        with self.lock:
            for e in reversed(self.events):
                if e.get("file") == file:
                    return e
        return None

    def last_by_box(self):
        with self.lock:
            out = {}
            for e in self.events:
                if e.get("label"):                         # last valid verdict (errors are counted, not shown here)
                    out[e["box"]] = e
        return out

    def status(self, model, thr_fire, thr_smoke):
        with self.lock:
            ms = list(self.ms)
            return {"ok": True, "model": model, "thresholds": {"fire": thr_fire, "smoke": thr_smoke},
                    "uptime_s": int(time.time() - self.started), "counts": dict(self.counts),
                    "model_ms": {"n": len(ms), "median": percentile(ms, .5), "p95": percentile(ms, .95), "max": max(ms) if ms else None},
                    "webhook": dict(self.webhook),
                    "boxes": {str(b): {"time": e["time"], "label": e["label"], "conf": e["conf"]} for b, e in self.last_by_box().items()}}
