"""Image preprocessing and ONNX classifier. Contract: input [1,3,224,224] float32 RGB (ImageNet normalisation),
output [1,3] logits ordered (background, fire, smoke)."""
import io
import time
from dataclasses import dataclass

import numpy as np
from PIL import Image

LABELS = ("background", "fire", "smoke")
SIZE = 224
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32).reshape(3, 1, 1)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32).reshape(3, 1, 1)


class ImageError(ValueError):
    pass


@dataclass
class Prediction:
    label: str
    conf: float
    probs: tuple
    ms: int
    boxes: tuple = ()          # detector only: ((class_name, score, x1, y1, x2, y2), ...) in image pixels


def preprocess(jpeg: bytes) -> np.ndarray:
    try:
        img = Image.open(io.BytesIO(jpeg))
        img.load()
        img = img.convert("RGB").resize((SIZE, SIZE), Image.BILINEAR)
    except Exception as e:
        raise ImageError(f"undecodable image: {type(e).__name__}") from e
    x = np.asarray(img, dtype=np.float32).transpose(2, 0, 1) / 255.0
    return ((x - MEAN) / STD)[None].astype(np.float32)


def softmax(z):
    z = np.asarray(z, dtype=np.float64)
    e = np.exp(z - z.max())
    return e / e.sum()


class OnnxClassifier:
    def __init__(self, path, name=None):
        import onnxruntime as ort
        self.sess = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        i, o = self.sess.get_inputs()[0], self.sess.get_outputs()[0]
        if len(i.shape) != 4 or i.shape[1] != 3:
            raise ValueError(f"model input must be [N,3,H,W], got {i.shape}")
        if o.shape[-1] != 3:
            raise ValueError(f"model output must have 3 logits, got {o.shape}")
        self.inp = i.name
        self.name = name or str(path).replace("\\", "/").split("/")[-1]

    def predict(self, jpeg: bytes) -> Prediction:
        x = preprocess(jpeg)
        t = time.perf_counter()
        logits = self.sess.run(None, {self.inp: x})[0].reshape(-1)
        ms = int(round((time.perf_counter() - t) * 1000))
        p = softmax(logits)
        k = int(p.argmax())
        return Prediction(LABELS[k], float(p[k]), tuple(float(v) for v in p), ms)
