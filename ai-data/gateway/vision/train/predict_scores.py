"""Runs the YOLO ONNX model over an image list and writes scores.csv (image, score_smoke, score_fire).

  python predict_scores.py MODEL.onnx DATA_ROOT LIST.txt scores.csv [--limit N]
With --mask-overlay the label and date regions are neutralised first; compare the two score files with evaluate.py (a large loss on the overlay slice = shortcut).
Image names are matched to split_v2.csv by file name. Uses the same decoder as the gateway service.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "python", "src")); sys.path.insert(0, HERE)
from gateway_vision.yolo import YoloOnnxClassifier  # noqa: E402
from overlay import mask_overlay  # noqa: E402
from overlay_probe import present, REG  # noqa: E402
import cv2  # noqa: E402
import numpy as np  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model"); ap.add_argument("root"); ap.add_argument("list"); ap.add_argument("out")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--mask-overlay", action="store_true", help="neutralise the D-Fire label and date stamp before scoring")
    a = ap.parse_args()
    c = YoloOnnxClassifier(a.model, thr_fire=0.0, thr_smoke=0.0)
    paths = [l.strip() for l in open(a.list) if l.strip()]
    if a.limit:
        paths = paths[: a.limit]
    with open(a.out, "w") as f:
        f.write("image,score_smoke,score_fire,overlay\n")
        for p in paths:
            full = p if os.path.isabs(p) else os.path.join(a.root, p)
            raw = open(full, "rb").read()
            img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
            g = img.mean(2)
            ov = int(present(g, REG["label"]) or present(g, REG["date"]))        # measured on the original
            if a.mask_overlay:
                ok, buf = cv2.imencode(".jpg", mask_overlay(img), [cv2.IMWRITE_JPEG_QUALITY, 95]); raw = buf.tobytes()
            dets, _ = c.detect(raw)
            ss = max([d[1] for d in dets if d[0] == "smoke"], default=0.0)
            sf = max([d[1] for d in dets if d[0] == "fire"], default=0.0)
            f.write(f"{os.path.basename(p)},{ss:.5f},{sf:.5f},{ov}\n")
    print(len(paths), "images ->", a.out)


if __name__ == "__main__":
    main()
