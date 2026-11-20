"""Measures how often D-Fire frames carry the burned-in 'CameraNNNN' label and date stamp, per image class.
Regions: the stamp boxes of overlay.py (LABEL_DET, DATE_DET), read off 1280x720 frames and checked visually:
  label  x 4.5-16 %, y 8-11.5 %    black box with white text
  date   x 81-99 %, y 88-91.5 %    black box with white text
Presence test: >= 50 % of the pixels under 30 and >= 3 % over 200 in the region.
  python overlay_probe.py DATA_ROOT SPLIT_CSV [--n 4000] [--seed 0] [--budget 140]
"""
import argparse, csv, os, random, time
import cv2
import numpy as np

from overlay import LABEL_DET, DATE_DET
REG = {"label": LABEL_DET, "date": DATE_DET}


def present(g, reg):
    x0, x1, y0, y1 = reg
    h, w = g.shape
    r = g[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)]
    return bool((r < 30).mean() >= 0.5 and (r > 200).mean() >= 0.03)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("root"); ap.add_argument("split_csv")
    ap.add_argument("--n", type=int, default=4000); ap.add_argument("--seed", type=int, default=0); ap.add_argument("--budget", type=float, default=140)
    a = ap.parse_args()
    rows = list(csv.DictReader(open(a.split_csv))); random.Random(a.seed).shuffle(rows)
    t0 = time.time(); out = []
    for r in rows[: a.n]:
        if time.time() - t0 > a.budget: break
        g = cv2.imread(f"{a.root}/data/{r['orig_split']}/images/{r['image']}", cv2.IMREAD_REDUCED_GRAYSCALE_2)
        if g is None: continue
        out.append((r["class"], float(r["lum"]), present(g, REG["label"]), present(g, REG["date"])))
    print(f"{len(out)} images")
    for c in ("background", "smoke", "fire", "both"):
        o = [x for x in out if x[0] == c]
        print(f"{c:10s} n={len(o):5d} label {np.mean([x[2] for x in o])*100:5.1f}%  date {np.mean([x[3] for x in o])*100:5.1f}%  either {np.mean([x[2] or x[3] for x in o])*100:5.1f}%")
    anyo = np.array([x[2] or x[3] for x in out]); y = np.array([x[0] != "background" for x in out]); lum = np.array([x[1] for x in out])
    print(f"P(fire/smoke | overlay) = {y[anyo].mean():.2f}   P(fire/smoke | no overlay) = {y[~anyo].mean():.2f}   overlay share {anyo.mean():.2f}")
    d = lum < 40
    print(f"dark images: overlay share {anyo[d].mean():.2f}; P(positive | dark & overlay) = {y[d & anyo].mean():.2f} (n={int((d & anyo).sum())}); P(positive | dark & no overlay) = {y[d & ~anyo].mean():.2f} (n={int((d & ~anyo).sum())})")
