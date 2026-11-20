"""Writes degraded copies of training images (OV2640-like) with the same labels.

  python build_degraded.py DATA_ROOT SPLIT_CSV OUT_DIR [--per-image 1] [--severity 0.6] [--flare-frac 0.15] [--limit N] [--seed 0]

Output: OUT_DIR/images/*.jpg, OUT_DIR/labels/*.txt (copied; geometry unchanged) and OUT_DIR/train_deg.txt, to append
to the training list. Only images of the TRAIN split are degraded: val and test stay untouched, so they measure the
clean domain; degrade val/test copies separately (--split val) to measure robustness.
The burned-in D-Fire overlay (camera label, date) is masked on a share of the images that have one and a synthetic one is pasted on a share of those that do not, with the same probabilities for every class, so it stops predicting the label (overlay.py).
Flare and night-like darkening are added only to images without any label (synthetic hard negatives).
"""
import argparse
import csv
import os
import shutil
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from degrade import degrade, flare, night
from overlay import mask_overlay, paste_overlay
from overlay_probe import present, REG  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root"); ap.add_argument("split_csv"); ap.add_argument("out")
    ap.add_argument("--split", default="train"); ap.add_argument("--per-image", type=int, default=1)
    ap.add_argument("--severity", type=float, default=0.6); ap.add_argument("--flare-frac", type=float, default=0.15); ap.add_argument("--night-frac", type=float, default=0.25)
    ap.add_argument("--mask-frac", type=float, default=0.35); ap.add_argument("--paste-frac", type=float, default=0.25)
    ap.add_argument("--limit", type=int, default=0); ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    os.makedirs(f"{a.out}/images", exist_ok=True); os.makedirs(f"{a.out}/labels", exist_ok=True)
    rng = np.random.default_rng(a.seed)
    rows = [r for r in csv.DictReader(open(a.split_csv)) if r["new_split"] == a.split]
    if a.limit:
        rows = rows[: a.limit]
    paths, nflare, nnight, nmask, npaste = [], 0, 0, 0, 0
    for r in rows:
        stem = r["image"].rsplit(".", 1)[0]
        src = f"{a.root}/data/{r['orig_split']}/images/{r['image']}"
        lab = f"{a.root}/data/{r['orig_split']}/labels/{stem}.txt"
        img = cv2.imread(src)
        if img is None:
            continue
        img = img[..., ::-1]
        for k in range(a.per_image):
            x = img
            if r["class"] == "background":
                u = rng.random()
                if u < a.night_frac:
                    x = night(x, rng); nnight += 1
                elif u < a.night_frac + a.flare_frac:
                    x = flare(x, rng, rng.uniform(0.5, 1.0)); nflare += 1
            has = present(x.mean(2), REG["label"]) or present(x.mean(2), REG["date"])
            u = rng.random()                                   # same probabilities for every class: the overlay carries no label
            if has and u < a.mask_frac:
                x = mask_overlay(x); nmask += 1
            elif not has and u < a.paste_frac:
                x = paste_overlay(x, rng); npaste += 1
            x, _ = degrade(x, rng, a.severity)
            name = f"{stem}_d{k}"
            cv2.imwrite(f"{a.out}/images/{name}.jpg", x[..., ::-1], [cv2.IMWRITE_JPEG_QUALITY, 92])
            shutil.copyfile(lab, f"{a.out}/labels/{name}.txt")
            paths.append(os.path.abspath(f"{a.out}/images/{name}.jpg").replace(os.sep, "/"))
    open(f"{a.out}/{a.split}_deg.txt", "w").write("\n".join(paths) + "\n")
    print(f"{len(paths)} degraded images ({nflare} with flare, {nnight} night-like negatives, {nmask} overlays masked, {npaste} synthetic overlays pasted) -> {a.out}")


if __name__ == "__main__":
    main()
