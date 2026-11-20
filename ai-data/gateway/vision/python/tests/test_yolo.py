"""Decoder and decision rule with hand-made network outputs (no model needed)."""
import io
import numpy as np
import pytest
from PIL import Image
from gateway_vision.yolo import YoloOnnxClassifier, letterbox, nms, decode, decide

NAMES = {0: "smoke", 1: "fire"}


def jpeg(w=1280, h=720, rgb=(80, 120, 70)):
    b = io.BytesIO(); Image.new("RGB", (w, h), rgb).save(b, "JPEG"); return b.getvalue()


def out_tensor(dets, n=8400, nc=2):
    """dets: list of (cls, score, cx, cy, w, h) in 640x640 letterbox pixels."""
    t = np.zeros((1, 4 + nc, n), np.float32)
    for i, (c, s, cx, cy, w, h) in enumerate(dets):
        t[0, :4, i] = (cx, cy, w, h); t[0, 4 + c, i] = s
    return t


class FakeSession:
    def __init__(self, tensor): self.t = tensor
    def get_inputs(self):
        class I: name = "images"; shape = [1, 3, 640, 640]
        return [I()]
    def get_modelmeta(self):
        class M: custom_metadata_map = {"names": "{0: 'smoke', 1: 'fire'}"}
        return M()
    def run(self, _, feed):
        assert feed["images"].shape == (1, 3, 640, 640) and feed["images"].dtype == np.float32
        return [self.t]


def test_letterbox_geometry():
    img = Image.new("RGB", (1280, 720)); lb, r, px, py = letterbox(img, 640)
    assert lb.size == (640, 640) and r == 0.5 and px == 0 and py == 140


def test_box_is_mapped_back_to_the_original_image():
    # a fire box centred at (320, 300) of the letterbox, 40 x 30: original = ((x - 0) / 0.5, (y - 140) / 0.5)
    c = YoloOnnxClassifier(session=FakeSession(out_tensor([(1, 0.8, 320, 300, 40, 30)])))
    dets, _ = c.detect(jpeg())
    name, s, x1, y1, x2, y2 = dets[0]
    assert name == "fire" and abs(s - 0.8) < 1e-6
    assert (x1, y1, x2, y2) == pytest.approx((600, 290, 680, 350), abs=1e-3)


def test_nms_merges_duplicates_but_keeps_different_classes_and_far_boxes():
    t = out_tensor([(1, 0.9, 300, 300, 50, 50), (1, 0.7, 305, 302, 50, 50), (0, 0.6, 300, 300, 50, 50), (1, 0.5, 500, 400, 50, 50)])
    c = YoloOnnxClassifier(session=FakeSession(t))
    d, _ = c.detect(jpeg())
    assert sorted((x[0], round(x[1], 1)) for x in d) == [("fire", 0.5), ("fire", 0.9), ("smoke", 0.6)]


def test_decision_rule():
    f = lambda dets, tf=0.25, ts=0.25: decide(dets, tf, ts)[:2]
    assert f([]) == ("background", 1.0)
    assert f([("smoke", 0.4, 0, 0, 1, 1)]) == ("smoke", 0.4)
    assert f([("fire", 0.3, 0, 0, 1, 1), ("smoke", 0.9, 0, 0, 1, 1)]) == ("fire", 0.3)      # fire wins
    assert f([("fire", 0.2, 0, 0, 1, 1)]) == ("background", pytest.approx(0.8))                # below the threshold
    assert f([("fire", 0.2, 0, 0, 1, 1)], tf=0.1) == ("fire", 0.2)


def test_predict_and_class_order_from_metadata():
    c = YoloOnnxClassifier(session=FakeSession(out_tensor([(0, 0.7, 320, 320, 200, 200)])))
    p = c.predict(jpeg())
    assert p.label == "smoke" and abs(p.conf - 0.7) < 1e-6 and len(p.boxes) == 1 and abs(sum(p.probs[1:]) - 0.7) < 1e-6
    with pytest.raises(ValueError):
        YoloOnnxClassifier(session=FakeSession(out_tensor([])), names={0: "a", 1: "b"})
    from gateway_vision.classifier import ImageError
    with pytest.raises(ImageError):
        c.predict(b"not an image")


def test_works_in_the_http_service():
    import json, threading, urllib.request
    from gateway_vision.server import make_server
    c = YoloOnnxClassifier(session=FakeSession(out_tensor([(1, 0.9, 320, 300, 40, 30)])))
    s = make_server(c, "127.0.0.1", 0, None)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    rq = urllib.request.Request(f"http://127.0.0.1:{s.server_port}/v1/frame", data=jpeg(),
                                headers={"X-Box-Id": "1", "X-Req-Id": "9"}, method="POST")
    d = json.loads(urllib.request.urlopen(rq).read()); s.shutdown()
    assert d["label"] == "fire" and d["id"] == 9 and d["conf"] == 0.9
