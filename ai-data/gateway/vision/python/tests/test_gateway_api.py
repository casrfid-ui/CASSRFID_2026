"""Gateway API beyond the box protocol: detailed result, status, events, annotated photo, webhook. Fake classifier, no model needed."""
import io, json, threading, time, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer
import pytest
from PIL import Image
from gateway_vision.classifier import Prediction, ImageError
from gateway_vision.server import make_server


class Fake:
    name = "fake.onnx"; thr_fire = 0.3; thr_smoke = 0.2

    def __init__(self):
        self.next = Prediction("background", 0.9, (0.9, 0.05, 0.05), 5)

    def predict(self, jpeg):
        if jpeg == b"bad":
            raise ImageError("undecodable image")
        return self.next


def jpg(w=200, h=100):
    b = io.BytesIO(); Image.new("RGB", (w, h), (90, 120, 60)).save(b, "JPEG"); return b.getvalue()


def call(url, data=None, headers=None, method=None):
    req = urllib.request.Request(url, data, headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read(), r.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers


@pytest.fixture
def gw(tmp_path):
    hook = []

    class W(BaseHTTPRequestHandler):
        def do_POST(self):
            hook.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(200); self.send_header("Content-Length", "0"); self.end_headers()

        def log_message(self, *a): pass
    w = HTTPServer(("127.0.0.1", 0), W); threading.Thread(target=w.serve_forever, daemon=True).start()
    f = Fake()
    s = make_server(f, "127.0.0.1", 0, store=tmp_path / "rx", webhook=f"http://127.0.0.1:{w.server_port}/h")
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield f, f"http://127.0.0.1:{s.server_port}", hook, tmp_path / "rx", s
    s.shutdown(); w.shutdown()


def frame(url, rid, box=1, t=1000):
    return call(url + "/v1/frame", jpg(), {"X-Box-Id": str(box), "X-Req-Id": str(rid), "X-Time": str(t), "X-Reasons": "3"})


def test_predict_detail_has_alert_and_normalised_boxes(gw):
    f, url, *_ = gw
    f.next = Prediction("fire", 0.8, (0.1, 0.8, 0.1), 7, (("fire", 0.8, 20.0, 10.0, 60.0, 40.0), ("smoke", 0.4, 0.0, 0.0, 100.0, 50.0)))
    st, body, _ = call(url + "/v1/predict", jpg())
    d = json.loads(body)
    assert st == 200 and d["alert"] == "fire" and d["detected"] is True and d["label"] == "fire"
    assert d["image"] == {"width": 200, "height": 100} and d["thresholds"] == {"fire": 0.3, "smoke": 0.2}
    assert d["detections"][0]["box_norm"] == [0.1, 0.1, 0.3, 0.4] and d["detections"][1]["class"] == "smoke"
    f.next = Prediction("background", 0.95, (0.95, 0.03, 0.02), 4)
    d = json.loads(call(url + "/v1/predict", jpg())[1])
    assert d["alert"] == "none" and d["detected"] is False and d["detections"] == []


def test_predict_errors(gw):
    _, url, *_ = gw
    assert call(url + "/v1/predict", b"bad")[0] == 400
    assert call(url + "/v1/predict", b"", method="POST")[0] == 400


def test_status_events_and_filters(gw):
    f, url, hook, rx, srv = gw
    f.next = Prediction("smoke", 0.6, (0.2, 0.2, 0.6), 11, (("smoke", 0.6, 1.0, 2.0, 50.0, 40.0),))
    assert frame(url, 1, box=1)[0] == 200
    f.next = Prediction("background", 0.9, (0.9, 0.05, 0.05), 5)
    frame(url, 2, box=2)
    f.next = Prediction("fire", 0.7, (0.1, 0.7, 0.2), 13, (("fire", 0.7, 5.0, 5.0, 30.0, 30.0),))
    frame(url, 3, box=1, t=1010)
    assert call(url + "/v1/frame", b"bad", {"X-Box-Id": "1", "X-Req-Id": "4", "X-Time": "1", "X-Reasons": "0"})[0] == 400
    s = json.loads(call(url + "/v1/status")[1])
    assert s["counts"] == {"fire": 1, "smoke": 1, "background": 1, "error": 1} and s["model"] == "fake.onnx"
    assert s["model_ms"]["n"] == 3 and s["model_ms"]["median"] == 11
    assert s["boxes"]["1"]["label"] == "fire" and s["boxes"]["2"]["label"] == "background"
    ev = json.loads(call(url + "/v1/events?limit=10")[1])["events"]
    assert [e["req"] for e in ev] == [4, 3, 2, 1]                       # newest first
    only = json.loads(call(url + "/v1/events?label=fire")[1])["events"]
    assert [e["req"] for e in only] == [3] and only[0]["alert"] == "fire" and only[0]["size"] == [200, 100]
    assert [e["req"] for e in json.loads(call(url + "/v1/events?box=2")[1])["events"]] == [2]
    assert call(url + "/v1/events?limit=x")[0] == 400


def test_stored_photo_plain_and_annotated(gw):
    f, url, hook, rx, _ = gw
    f.next = Prediction("fire", 0.7, (0.1, 0.7, 0.2), 13, (("fire", 0.7, 5.0, 5.0, 60.0, 60.0),))
    frame(url, 7, box=3, t=2000)
    st, plain, h = call(url + "/v1/events/b3_2000_7.jpg")
    st2, ann, _ = call(url + "/v1/events/b3_2000_7.jpg?annotated=1")
    assert st == st2 == 200 and h["Content-Type"] == "image/jpeg" and plain != ann
    assert Image.open(io.BytesIO(ann)).size == (200, 100)
    assert call(url + "/v1/events/../../etc/passwd")[0] == 404
    assert call(url + "/v1/events/b9_9_9.jpg")[0] == 404


def test_webhook_only_for_fire_and_smoke(gw):
    f, url, hook, *_ = gw
    f.next = Prediction("background", 0.9, (0.9, 0.05, 0.05), 5)
    frame(url, 1)
    f.next = Prediction("fire", 0.7, (0.1, 0.7, 0.2), 13)
    frame(url, 2, box=5)
    for _ in range(50):
        if hook: break
        time.sleep(0.05)
    assert len(hook) == 1 and hook[0]["event"]["label"] == "fire" and hook[0]["event"]["box"] == 5


def test_history_reloaded_after_restart(gw):
    f, url, hook, rx, srv = gw
    f.next = Prediction("fire", 0.7, (0.1, 0.7, 0.2), 13)
    frame(url, 1)
    s2 = make_server(f, "127.0.0.1", 0, store=rx)
    assert [e["req"] for e in s2.events.recent()] == [1]
    s2.server_close()


def test_box_protocol_unchanged(gw):
    f, url, *_ = gw
    f.next = Prediction("smoke", 0.61234, (0.2, 0.2, 0.6), 11)
    st, body, _ = frame(url, 9)
    assert st == 200 and json.loads(body) == {"v": 1, "id": 9, "label": "smoke", "conf": 0.6123, "ms": 11}
