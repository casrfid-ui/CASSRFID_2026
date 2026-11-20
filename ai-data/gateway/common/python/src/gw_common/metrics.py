"""Metrics for rare-event prediction, with confidence intervals that respect correlated samples.

Consecutive days (or scans) are not independent: the bootstrap resamples whole **blocks** (a block id per sample),
never single samples."""
import numpy as np


def _rank(x):
    """Average ranks (ties share the mean rank), 1-based."""
    x = np.asarray(x, float)
    order = np.argsort(x, kind="mergesort")
    r = np.empty(len(x))
    xs = x[order]
    i = 0
    while i < len(x):
        j = i
        while j + 1 < len(x) and xs[j + 1] == xs[i]:
            j += 1
        r[order[i:j + 1]] = 0.5 * (i + j) + 1.0
        i = j + 1
    return r


def auc(y, s):
    """ROC AUC by the rank statistic. NaN if one class is missing."""
    y = np.asarray(y).astype(bool)
    n1, n0 = int(y.sum()), int((~y).sum())
    if n1 == 0 or n0 == 0:
        return float("nan")
    r = _rank(s)
    return float((r[y].sum() - n1 * (n1 + 1) / 2.0) / (n1 * n0))


def average_precision(y, s):
    """Area under the precision-recall curve as sum over positives of precision at that rank (step form, ties broken by order)."""
    y = np.asarray(y).astype(bool)
    if y.sum() == 0:
        return float("nan")
    o = np.argsort(-np.asarray(s, float), kind="mergesort")
    yo = y[o]
    tp = np.cumsum(yo)
    prec = tp / (np.arange(len(yo)) + 1.0)
    return float(prec[yo].sum() / y.sum())


def brier(y, p):
    y = np.asarray(y, float)
    return float(np.mean((np.asarray(p, float) - y) ** 2))


def reliability(y, p, bins=10):
    """Equal-width bins on [0,1]: (mean predicted, observed rate, count) per non-empty bin."""
    y, p = np.asarray(y, float), np.asarray(p, float)
    idx = np.minimum((p * bins).astype(int), bins - 1)
    out = []
    for b in range(bins):
        m = idx == b
        if m.any():
            out.append((float(p[m].mean()), float(y[m].mean()), int(m.sum())))
    return out


def ece(p, y, bins=10):
    """Expected calibration error (equal-width bins)."""
    rel = reliability(y, p, bins)
    n = sum(c for _, _, c in rel)
    return float(sum(c * abs(a - b) for a, b, c in rel) / n) if n else float("nan")


def far_at_recall(y, s, recall):
    """Smallest false-positive rate among thresholds that reach `recall`. Returns (fpr, threshold)."""
    y = np.asarray(y).astype(bool)
    s = np.asarray(s, float)
    pos = np.sort(s[y])[::-1]
    if len(pos) == 0 or (~y).sum() == 0:
        return float("nan"), float("nan")
    thr = pos[int(np.ceil(recall * len(pos))) - 1]
    return float((s[~y] >= thr).mean()), float(thr)


class PlattCalibrator:
    """P(y=1|s) = sigmoid(a * logit(s) + b), s clipped to [eps, 1-eps]; Newton iterations."""

    def __init__(self, eps=1e-4):
        self.eps, self.a, self.b = eps, 1.0, 0.0

    def _x(self, s):
        s = np.clip(np.asarray(s, float), self.eps, 1 - self.eps)
        return np.log(s / (1 - s))

    def fit(self, s, y, iters=50, ridge=1e-6):
        x, y = self._x(s), np.asarray(y, float)
        w = np.array([1.0, 0.0])
        X = np.stack([x, np.ones_like(x)], 1)
        for _ in range(iters):
            p = 1.0 / (1.0 + np.exp(-X @ w))
            g = X.T @ (p - y) + ridge * w
            H = (X * (p * (1 - p))[:, None]).T @ X + ridge * np.eye(2)
            step = np.linalg.solve(H, g)
            w = w - step
            if np.abs(step).max() < 1e-9:
                break
        self.a, self.b = float(w[0]), float(w[1])
        return self

    def predict(self, s):
        return 1.0 / (1.0 + np.exp(-(self.a * self._x(s) + self.b)))


def _blocks(blocks):
    blocks = np.asarray(blocks)
    ids, inv = np.unique(blocks, return_inverse=True)
    members = [np.flatnonzero(inv == k) for k in range(len(ids))]
    return members


def block_bootstrap(metric, y, s, blocks, n=1000, seed=0, level=0.95):
    """(point, low, high) of metric(y, s) with whole blocks resampled."""
    y, s = np.asarray(y), np.asarray(s)
    members = _blocks(blocks)
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n):
        pick = rng.integers(0, len(members), len(members))
        idx = np.concatenate([members[k] for k in pick])
        v = metric(y[idx], s[idx])
        if not np.isnan(v):
            vals.append(v)
    a = (1 - level) / 2
    lo, hi = (np.quantile(vals, [a, 1 - a]) if vals else (float("nan"),) * 2)
    return float(metric(y, s)), float(lo), float(hi)


def paired_block_bootstrap(metric, y, s1, s2, blocks, n=1000, seed=0, level=0.95):
    """(difference, low, high) of metric(y, s1) - metric(y, s2); the same blocks are drawn for both scores."""
    y, s1, s2 = np.asarray(y), np.asarray(s1), np.asarray(s2)
    members = _blocks(blocks)
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n):
        pick = rng.integers(0, len(members), len(members))
        idx = np.concatenate([members[k] for k in pick])
        d = metric(y[idx], s1[idx]) - metric(y[idx], s2[idx])
        if not np.isnan(d):
            vals.append(d)
    a = (1 - level) / 2
    lo, hi = (np.quantile(vals, [a, 1 - a]) if vals else (float("nan"),) * 2)
    return float(metric(y, s1) - metric(y, s2)), float(lo), float(hi)
