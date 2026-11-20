"""Gateway HTTP service.  python -m gateway_vision.server --model fire_smoke_yolo.onnx --thresholds thresholds.json --port 8080 --store received

Box protocol (unchanged, what the box firmware calls):
  POST /v1/frame             body JPEG, headers X-Box-Id X-Req-Id X-Time X-Reasons -> {"v":1,"id":N,"label":"fire|smoke|background","conf":c,"ms":m}
  POST /v1/frame?debug=1     same + "boxes" (for people, never used by the box)
For people, the dashboard and tests:
  POST /v1/predict           body JPEG, no headers, nothing stored -> full result: alert, detections with pixel and normalised boxes
  GET  /v1/status            model, thresholds, counters, model latency (median, p95), last verdict per box
  GET  /v1/events?limit=&label=&box=   recent events, newest first
  GET  /v1/events/<file>.jpg[?annotated=1]   the stored photo, optionally with the boxes drawn
  GET  /health
--webhook URL: every fire or smoke verdict received on /v1/frame is also POSTed to URL as JSON ({"event": {...}})."""
import argparse
import io
import json
import re
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

from .classifier import ImageError
from .events import ALERTS, EventLog
from .protocol import error, ok

MAX_BODY = 2 * 1024 * 1024
FILE_RE = re.compile(r"^b\d+_\d+_\d+\.jpg$")


def _size(jpeg):
    from PIL import Image
    try:
        return list(Image.open(io.BytesIO(jpeg)).size)
    except Exception:
        return None


def detail(pred, size, classifier):
    """Full, human-oriented result of one photo."""
    w, h = size or (None, None)
    dets = []
    for c, sc, x1, y1, x2, y2 in pred.boxes:
        d = {"class": c, "score": round(float(sc), 4), "box_px": [round(v, 1) for v in (x1, y1, x2, y2)]}
        if w:
            d["box_norm"] = [round(x1 / w, 4), round(y1 / h, 4), round(x2 / w, 4), round(y2 / h, 4)]
        dets.append(d)
    return {"alert": pred.label if pred.label in ALERTS else "none", "detected": pred.label in ALERTS,
            "label": pred.label, "conf": round(float(pred.conf), 4), "ms": int(pred.ms), "image": {"width": w, "height": h},
            "detections": dets, "model": classifier.name,
            "thresholds": {"fire": getattr(classifier, "thr_fire", None), "smoke": getattr(classifier, "thr_smoke", None)}}


def make_server(classifier, host="127.0.0.1", port=8080, store=None, quiet=True, webhook=None, keep=500):
    lock = threading.Lock()                     # one inference at a time
    store = Path(store) if store else None
    if store:
        store.mkdir(parents=True, exist_ok=True)
    events = EventLog(store, keep)

    def notify(rec):
        def run():
            try:
                req = urllib.request.Request(webhook, json.dumps({"event": rec}).encode(), {"Content-Type": "application/json"})
                urllib.request.urlopen(req, timeout=3).read()
                events.webhook["sent"] += 1
            except Exception:
                events.webhook["failed"] += 1
        threading.Thread(target=run, daemon=True).start()

    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            if not quiet:
                super().log_message(*a)

        def _send(self, code, body, ctype="application/json"):
            b = body if isinstance(body, bytes) else body.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(b)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            u = urlsplit(self.path); q = parse_qs(u.query)
            if u.path == "/health":
                return self._send(200, json.dumps({"ok": True, "model": classifier.name}))
            if u.path == "/v1/status":
                return self._send(200, json.dumps(events.status(classifier.name, getattr(classifier, "thr_fire", None), getattr(classifier, "thr_smoke", None))))
            if u.path == "/v1/events":
                try:
                    limit = max(1, min(500, int(q.get("limit", ["50"])[0])))
                    box = int(q["box"][0]) if "box" in q else None
                except ValueError:
                    return self._send(400, error(0, "bad query"))
                return self._send(200, json.dumps({"events": events.recent(limit, q.get("label", [None])[0], box)}))
            if u.path.startswith("/v1/events/"):
                name = u.path.rsplit("/", 1)[1]
                if not store or not FILE_RE.match(name) or not (store / name).exists():
                    return self._send(404, error(0, "not found"))
                data = (store / name).read_bytes()
                rec = events.find(name)
                if q.get("annotated") == ["1"] and rec and rec.get("boxes"):
                    from .client import draw_boxes
                    buf = io.BytesIO()
                    draw_boxes(data, rec["boxes"], buf, label=f"{rec['label']} {rec['conf']}")
                    data = buf.getvalue()
                return self._send(200, data, "image/jpeg")
            self._send(404, error(0, "not found"))

        def _body(self, req_id):
            """Returns the JPEG, or None after having answered an error."""
            n = int(self.headers.get("Content-Length", "0") or 0)
            if n <= 0:
                self._send(400, error(req_id, "empty body")); return None
            if n > MAX_BODY:
                left = min(n, 16 * MAX_BODY)            # read and drop (bounded) so the client sees the answer
                while left > 0:
                    chunk = self.rfile.read(min(65536, left))
                    if not chunk:
                        break
                    left -= len(chunk)
                self.close_connection = True
                self._send(413, error(req_id, "too large")); return None
            return self.rfile.read(n)

        def do_POST(self):
            req_id = 0
            u = urlsplit(self.path)
            debug = parse_qs(u.query).get("debug") == ["1"]
            if u.path == "/v1/predict":
                jpeg = self._body(0)
                if jpeg is None:
                    return
                try:
                    with lock:
                        pred = classifier.predict(jpeg)
                except ImageError as e:
                    return self._send(400, error(0, str(e)))
                except Exception as e:
                    return self._send(500, error(0, "model failure"))
                return self._send(200, json.dumps(detail(pred, _size(jpeg), classifier)))
            try:
                req_id = int(self.headers.get("X-Req-Id", ""))
                box_id = int(self.headers.get("X-Box-Id", ""))
                unix_s = int(self.headers.get("X-Time", "0"))
                reasons = int(self.headers.get("X-Reasons", "0"))
            except ValueError:
                self._drain(); return self._send(400, error(req_id, "bad headers"))
            if u.path != "/v1/frame":
                self._drain(); return self._send(404, error(req_id, "not found"))
            jpeg = self._body(req_id)
            if jpeg is None:
                return
            try:
                with lock:
                    pred = classifier.predict(jpeg)
            except ImageError as e:
                self._record(box_id, req_id, unix_s, reasons, jpeg, None, str(e))
                return self._send(400, error(req_id, str(e)))
            except Exception as e:
                self._record(box_id, req_id, unix_s, reasons, jpeg, None, f"model: {type(e).__name__}")
                return self._send(500, error(req_id, "model failure"))
            rec = self._record(box_id, req_id, unix_s, reasons, jpeg, pred, None)
            self._send(200, ok(req_id, pred.label, pred.conf, pred.ms, pred.boxes if debug else None))
            if webhook and rec["label"] in ALERTS:
                notify(rec)

        def _drain(self):
            n = int(self.headers.get("Content-Length", "0") or 0)
            if 0 < n <= MAX_BODY:
                self.rfile.read(n)

        @staticmethod
        def _record(box_id, req_id, unix_s, reasons, jpeg, pred, err):
            stem = f"b{box_id}_{unix_s}_{req_id}"
            if store:
                (store / f"{stem}.jpg").write_bytes(jpeg)
            rec = {"box": box_id, "req": req_id, "time": unix_s, "reasons": reasons, "received": time.time(),
                   "file": f"{stem}.jpg" if store else None,
                   "label": pred.label if pred else None, "alert": (pred.label if pred.label in ALERTS else "none") if pred else None,
                   "conf": round(float(pred.conf), 4) if pred else None,
                   "probs": [round(float(p), 4) for p in pred.probs] if pred else None, "ms": pred.ms if pred else None,
                   "boxes": [[b[0], round(float(b[1]), 4), *[round(float(v), 1) for v in b[2:]]] for b in pred.boxes] if pred else None,
                   "size": _size(jpeg), "error": err}
            events.add(rec)
            return rec

    srv = ThreadingHTTPServer((host, port), H)
    srv.events = events
    return srv


def build_classifier(model, kind="yolo", thr_fire=0.25, thr_smoke=0.25, thresholds_json=None):
    """kind 'yolo' (detector, the intended model) or 'cls' (224 px 3-logit classifier). thresholds_json: file written by the
    training notebook ({"thr_fire": .., "thr_smoke": ..}); it overrides the two numbers."""
    if thresholds_json:
        t = json.load(open(thresholds_json))
        thr_fire, thr_smoke = float(t["thr_fire"]), float(t["thr_smoke"])
    if kind == "yolo":
        from .yolo import YoloOnnxClassifier
        return YoloOnnxClassifier(model, thr_fire=thr_fire, thr_smoke=thr_smoke)
    from .classifier import OnnxClassifier
    return OnnxClassifier(model)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--kind", choices=["yolo", "cls"], default="yolo")
    ap.add_argument("--thr-fire", type=float, default=0.25); ap.add_argument("--thr-smoke", type=float, default=0.25)
    ap.add_argument("--thresholds", default=None, help="thresholds.json written by the notebook")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--store", default="received")
    ap.add_argument("--webhook", default=None, help="URL that receives every fire/smoke event as JSON")
    a = ap.parse_args()
    clf = build_classifier(a.model, a.kind, a.thr_fire, a.thr_smoke, a.thresholds)
    srv = make_server(clf, a.host, a.port, a.store, quiet=False, webhook=a.webhook)
    print(f"{clf.name} listening on {a.host}:{a.port}")
    srv.serve_forever()
