"""Client and service together, with a hand-made detector (no model file)."""
import io, json, threading
import numpy as np
from PIL import Image
from gateway_vision.yolo import YoloOnnxClassifier
from gateway_vision.server import make_server
from gateway_vision.client import send_photo, draw_boxes, main

NAMES = {0: "smoke", 1: "fire"}


def jpeg(w=1280, h=720):
    b = io.BytesIO(); Image.new("RGB", (w, h), (80, 120, 70)).save(b, "JPEG"); return b.getvalue()


class Fake:
    def __init__(self, dets): self.t = np.zeros((1, 6, 200), np.float32); [self.t.__setitem__((0, slice(0, 4), i), d[2:6]) or self.t.__setitem__((0, 4 + d[0], i), d[1]) for i, d in enumerate(dets)]
    def get_inputs(self):
        class I: name = "images"; shape = [1, 3, 640, 640]
        return [I()]
    def get_modelmeta(self):
        class M: custom_metadata_map = {"names": "{0: 'smoke', 1: 'fire'}"}
        return M()
    def run(self, _, feed): return [self.t]


def serve(dets):
    s = make_server(YoloOnnxClassifier(session=Fake(dets)), "127.0.0.1", 0, None)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s, f"http://127.0.0.1:{s.server_port}"


def test_send_photo_plain_and_debug():
    s, url = serve([(1, 0.9, 320, 300, 40, 30)])
    r = send_photo(url, jpeg(), box_id=3, req_id=11)
    assert r["status"] == 200 and r["answer"]["label"] == "fire" and r["answer"]["id"] == 11 and "boxes" not in r["answer"]
    r = send_photo(url, jpeg(), req_id=12, debug=True)
    b = r["answer"]["boxes"][0]
    assert b[0] == "fire" and abs(b[1] - 0.9) < 1e-3 and b[2:] == [600.0, 290.0, 680.0, 350.0]
    assert len(json.dumps({"v": 1, "id": 12, "label": "fire", "conf": 0.9, "ms": 5}, separators=(",", ":"))) < 256    # what a box gets
    s.shutdown()


def test_errors_are_reported_not_raised():
    s, url = serve([])
    assert send_photo(url, b"not an image")["status"] == 400
    s.shutdown()
    r = send_photo(url, jpeg(), timeout=1.0)                       # server is down now
    assert r["status"] == 0 and "error" in r["answer"]


def test_cli_folder_annotate_and_csv(tmp_path):
    s, url = serve([(1, 0.8, 320, 300, 40, 30), (0, 0.6, 320, 200, 200, 120)])
    d = tmp_path / "in"; d.mkdir()
    for n in ("a.jpg", "b.jpg"): (d / n).write_bytes(jpeg())
    rows = main([url, "--folder", str(d), "--annotate", str(tmp_path / "out"), "--csv", str(tmp_path / "r.csv")])
    s.shutdown()
    assert [r["label"] for r in rows] == ["fire", "fire"] and all(r["status"] == 200 for r in rows)
    assert (tmp_path / "out" / "a.jpg").exists() and (tmp_path / "r.csv").read_text().startswith("image,status,label")
