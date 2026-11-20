"""YOLO (Ultralytics v8 / v11 style) ONNX detector as the gateway classifier.

Model contract: input [1,3,S,S] float32 RGB 0..1 (letterboxed, grey 114), output [1,4+nc,N] = (cx, cy, w, h) in
input pixels then nc class scores already passed through a sigmoid. Class names come from the ONNX metadata that
Ultralytics writes (`names`), so the order in the data file (0 smoke, 1 fire) is not hard-coded here.

Image-level rule (the box asks for one label): fire if the best fire score >= thr_fire, else smoke if the best smoke
score >= thr_smoke, else background. Fire wins a tie (the safer error). `conf` is the best score of the chosen class,
or 1 - max(scores) for background. Scores of a detector are NOT calibrated probabilities (see FICHE).
"""
import ast
import io
import time

import numpy as np
from PIL import Image

from .classifier import ImageError, Prediction


def letterbox(img: Image.Image, size: int):
    w, h = img.size
    r = min(size / w, size / h)
    nw, nh = int(round(w * r)), int(round(h * r))
    canvas = Image.new("RGB", (size, size), (114, 114, 114))
    px, py = (size - nw) // 2, (size - nh) // 2
    canvas.paste(img.resize((nw, nh), Image.BILINEAR), (px, py))
    return canvas, r, px, py


def iou(a, b):
    x1, y1 = np.maximum(a[0], b[:, 0]), np.maximum(a[1], b[:, 1])
    x2, y2 = np.minimum(a[2], b[:, 2]), np.minimum(a[3], b[:, 3])
    inter = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1]) - inter + 1e-9)


def nms(boxes, scores, thr):
    order = np.argsort(-scores); keep = []
    while len(order):
        i = order[0]; keep.append(int(i))
        if len(order) == 1:
            break
        order = order[1:][iou(boxes[i], boxes[order[1:]]) <= thr]
    return keep


def decode(out, names, r, px, py, orig_w, orig_h, conf_min=0.05, iou_thr=0.5, max_det=100):
    """out: [1,4+nc,N]. Returns a list of (class_name, score, x1, y1, x2, y2) in original image pixels."""
    p = np.asarray(out)[0].T                                  # [N, 4+nc]
    cx, cy, w, h = p[:, 0], p[:, 1], p[:, 2], p[:, 3]
    sc = p[:, 4:]
    res = []
    for c in range(sc.shape[1]):
        m = sc[:, c] >= conf_min
        if not m.any():
            continue
        b = np.stack([cx[m] - w[m] / 2, cy[m] - h[m] / 2, cx[m] + w[m] / 2, cy[m] + h[m] / 2], 1)
        s = sc[m, c]
        for i in nms(b, s, iou_thr):
            x1, y1, x2, y2 = (b[i] - [px, py, px, py]) / r
            res.append((names[c], float(s[i]), float(np.clip(x1, 0, orig_w)), float(np.clip(y1, 0, orig_h)),
                        float(np.clip(x2, 0, orig_w)), float(np.clip(y2, 0, orig_h))))
    res.sort(key=lambda d: -d[1])
    return res[:max_det]


def decide(dets, thr_fire, thr_smoke):
    sf = max([d[1] for d in dets if d[0] == "fire"], default=0.0)
    ss = max([d[1] for d in dets if d[0] == "smoke"], default=0.0)
    if sf >= thr_fire:
        label, conf = "fire", sf
    elif ss >= thr_smoke:
        label, conf = "smoke", ss
    else:
        label, conf = "background", 1.0 - max(sf, ss)
    return label, conf, (1.0 - max(sf, ss), sf, ss)


def providers():
    """GPU first when onnxruntime has it (gateway PC with CUDA), else CPU. The VIM4 NPU goes through its own runtime."""
    import onnxruntime as ort
    av = ort.get_available_providers()
    return [p for p in ("CUDAExecutionProvider", "CPUExecutionProvider") if p in av]


class YoloOnnxClassifier:
    def __init__(self, path=None, thr_fire=0.25, thr_smoke=0.25, names=None, session=None, size=None, name=None):
        if session is None:
            import onnxruntime as ort
            session = ort.InferenceSession(str(path), providers=providers())
        self.sess = session
        i = session.get_inputs()[0]
        self.inp = i.name
        self.size = size or int(i.shape[-1])
        if names is None:
            meta = session.get_modelmeta().custom_metadata_map.get("names")
            if not meta:
                raise ValueError("model has no `names` metadata: pass names={0: 'smoke', 1: 'fire'}")
            names = ast.literal_eval(meta)
        self.names = {int(k): str(v) for k, v in names.items()}
        if not {"fire", "smoke"} <= set(self.names.values()):
            raise ValueError(f"classes must include 'fire' and 'smoke', got {self.names}")
        self.thr_fire, self.thr_smoke = thr_fire, thr_smoke
        self.name = name or (str(path).replace("\\", "/").split("/")[-1] if path else "yolo")

    def detect(self, jpeg: bytes):
        try:
            img = Image.open(io.BytesIO(jpeg)); img.load(); img = img.convert("RGB")
        except Exception as e:
            raise ImageError(f"undecodable image: {type(e).__name__}") from e
        lb, r, px, py = letterbox(img, self.size)
        x = (np.asarray(lb, dtype=np.float32).transpose(2, 0, 1) / 255.0)[None]
        t = time.perf_counter()
        out = self.sess.run(None, {self.inp: x})[0]
        ms = int(round((time.perf_counter() - t) * 1000))
        return decode(out, self.names, r, px, py, img.size[0], img.size[1]), ms

    def predict(self, jpeg: bytes) -> Prediction:
        dets, ms = self.detect(jpeg)
        label, conf, probs = decide(dets, self.thr_fire, self.thr_smoke)
        return Prediction(label, float(conf), tuple(float(p) for p in probs), ms, tuple(dets))
