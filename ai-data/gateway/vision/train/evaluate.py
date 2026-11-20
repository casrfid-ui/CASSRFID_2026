"""Decision metrics from per-image detector scores (not box mAP: that comes from `yolo val`).

Input CSV (one row per image): image, score_smoke, score_fire  (from predict_scores.py); score_* = highest confidence of that class.
Group, image-level class (background / smoke / fire / both) and luminance come from split_v2.csv (--split-csv).
Alarm rule: the box asks for a photo; the gateway raises 'vision confirms' when max(score_smoke, score_fire) >= t
(or per class). Outputs, per class and for the alarm: AUC, average precision, the threshold and false-positive rate at a
target recall, expected false alarms per day for `--frames-per-day` photos, with 95 % CI by bootstrap over GROUPS
(near-duplicate groups, so correlated frames count once), and the same on slices (dark / bright / overlay).

  python evaluate.py scores.csv --split-csv ../../../data/vision_split/split_v2.csv --recall 0.9 --frames-per-day 2880
"""
import argparse
import csv
import sys

import numpy as np


def roc_ap(y, s):
    """AUC (rank based) and average precision. y in {0,1}."""
    y = np.asarray(y, bool); s = np.asarray(s, float)
    P, N = y.sum(), (~y).sum()
    if P == 0 or N == 0:
        return float("nan"), float("nan")
    order = np.argsort(-s, kind="mergesort"); ys = y[order]
    tp = np.cumsum(ys); fp = np.cumsum(~ys)
    _, inv, cnt = np.unique(s, return_inverse=True, return_counts=True)
    first = np.cumsum(cnt) - cnt + 1; avg = first + (cnt - 1) / 2.0
    r = avg[inv]
    auc = (r[y].sum() - P * (P + 1) / 2) / (P * N)
    prec = tp / (tp + fp); ap = float((prec * ys).sum() / P)
    return float(auc), ap


def op_at_recall(y, s, recall):
    """Largest threshold giving recall >= target, and the false-positive rate there."""
    y = np.asarray(y, bool); s = np.asarray(s, float)
    pos = np.sort(s[y])[::-1]
    if len(pos) == 0 or (~y).sum() == 0:
        return float("nan"), float("nan")
    k = int(np.ceil(recall * len(pos))) - 1
    t = pos[k]
    return float(t), float((s[~y] >= t).mean())


def bootstrap(groups, fn, n=500, seed=0):
    rng = np.random.default_rng(seed)
    ug, inv = np.unique(groups, return_inverse=True)
    idx_by = [np.nonzero(inv == i)[0] for i in range(len(ug))]
    vals = []
    for _ in range(n):
        pick = rng.integers(0, len(ug), len(ug))
        idx = np.concatenate([idx_by[i] for i in pick])
        v = fn(idx)
        if v == v:
            vals.append(v)
    return (float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))) if vals else (float("nan"),) * 2


def report(name, y, s, groups, recall, fpd, nboot, quiet=False):
    y = np.asarray(y, bool)
    if len(y) == 0 or y.sum() == 0 or (~y).sum() == 0:
        if not quiet:
            print(f"{name:16s} n={len(y):5d} pos={int(y.sum()):5d} skipped: needs at least one positive and one negative image")
        return None
    auc, ap = roc_ap(y, s)
    t, fpr = op_at_recall(y, s, recall)
    lo, hi = bootstrap(groups, lambda i: op_at_recall(y[i], s[i], recall)[1], nboot)
    if not quiet:
        print(f"{name:16s} n={len(y):5d} pos={int(np.sum(y)):5d} AUC={auc:.3f} AP={ap:.3f} | recall>={recall:.2f}: thr={t:.3f} "
              f"FPR={fpr:.4f} [{lo:.4f}, {hi:.4f}] -> false alarms/day={fpr * fpd:.1f} [{lo * fpd:.1f}, {hi * fpd:.1f}]")
    return dict(name=name, n=len(y), pos=int(y.sum()), auc=auc, ap=ap, thr=t, fpr=fpr, lo=lo, hi=hi, fa_day=fpr * fpd, fa_lo=lo * fpd, fa_hi=hi * fpd)


def load(scores_csv, split_csv):
    meta = {r["image"]: r for r in csv.DictReader(open(split_csv))}
    rows = list(csv.DictReader(open(scores_csv)))
    d = dict(
        image=[r["image"] for r in rows],
        cls=np.array([meta[r["image"]]["class"] for r in rows]),
        group=np.array([meta[r["image"]]["group"] for r in rows]),
        lum=np.array([float(meta[r["image"]]["lum"]) for r in rows]),
        ss=np.array([float(r["score_smoke"]) for r in rows]),
        sf=np.array([float(r["score_fire"]) for r in rows]),
        overlay=np.array([int(r["overlay"]) for r in rows]) == 1 if "overlay" in rows[0] else None)
    return d


def run(d, recall=0.9, fpd=2880.0, nboot=500, quiet=False):
    """Returns a list of result dicts (alarm, fire, smoke, then slices)."""
    cls, g = d["cls"], d["group"]
    anyp = np.maximum(d["ss"], d["sf"]); res = []
    for nm, y, s in [("alarm (any)", cls != "background", anyp), ("fire", (cls == "fire") | (cls == "both"), d["sf"]),
                     ("smoke", (cls == "smoke") | (cls == "both"), d["ss"])]:
        res.append(report(nm, y, s, g, recall, fpd, nboot, quiet))
    if not quiet:
        print("\nSlices (dark checks 'night = fire'; overlay checks the burned-in camera label and date stamp):")
    sl = [("dark (<40)", d["lum"] < 40), ("day (>=40)", d["lum"] >= 40)]
    if d["overlay"] is not None:
        sl += [("with overlay", d["overlay"]), ("no overlay", ~d["overlay"])]
    for nm, m in sl:
        res.append(report("alarm " + nm, (cls != "background")[m], anyp[m], g[m], recall, fpd, nboot, quiet))
    return [r for r in res if r]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scores"); ap.add_argument("--recall", type=float, default=0.9)
    ap.add_argument("--frames-per-day", type=float, default=2880.0, help="photos per day on a no-fire scene (worst case: one per 30 s)")
    ap.add_argument("--boot", type=int, default=500); ap.add_argument("--split-csv", required=True)
    a = ap.parse_args()
    d = load(a.scores, a.split_csv)
    print(f"{len(d['image'])} images; frames/day assumed {a.frames_per_day:.0f}; CI = bootstrap over groups\n")
    run(d, a.recall, a.frames_per_day, a.boot)


if __name__ == "__main__":
    main()
