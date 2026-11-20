"""Calibration of detector scores and sequential evidence (SPRT) over repeated photos of one box.

Why: one photo is a weak, noisy witness. In Suspicion the box can send a photo every 30 s; the gateway accumulates
evidence and raises 'vision confirms' only when it is strong enough, which cuts false alarms without a lower recall
per scene. This module is the statistical core; it knows nothing about HTTP or the box.

  PlattCalibrator   score -> P(event) by logistic regression, fitted on a validation set (never on train or test)
  ece()             expected calibration error (reliability)
  Sprt              Wald's sequential probability ratio test on per-frame log-likelihood ratios, with an optional
                    floor (the evidence cannot go below `floor`, so a long quiet period does not mask a later fire)
                    and a damping factor `rho` for correlated frames.

Limits (read before using the numbers):
  * Wald's error bounds hold for INDEPENDENT frames. Consecutive photos of one scene are correlated, so the real
    false-alarm rate of an undamped test is higher than alpha (tested below). rho < 1 shrinks each frame's weight;
    its value must be fitted on real sequences, which do not exist yet.
  * The prior of a fire is tiny in reality; the validation set is roughly half positive. The LLR below is
    prior-free (it uses the odds of the calibrated score divided by the odds of the validation prevalence).
"""
import numpy as np


def _sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -35, 35)))


class PlattCalibrator:
    """P(y=1 | s) = sigmoid(a * logit(s) + b), s clipped to [eps, 1-eps]. Newton iterations (IRLS)."""

    def __init__(self, eps=1e-4):
        self.eps, self.a, self.b, self.prevalence = eps, 1.0, 0.0, 0.5

    def _x(self, s):
        s = np.clip(np.asarray(s, float), self.eps, 1 - self.eps)
        return np.log(s / (1 - s))

    def fit(self, scores, y, iters=50, ridge=1e-6):
        x, y = self._x(scores), np.asarray(y, float)
        self.prevalence = float(y.mean())
        w = np.array([1.0, 0.0])
        X = np.stack([x, np.ones_like(x)], 1)
        for _ in range(iters):
            p = _sigmoid(X @ w)
            g = X.T @ (p - y) + ridge * w
            H = (X * (p * (1 - p))[:, None]).T @ X + ridge * np.eye(2)
            step = np.linalg.solve(H, g)
            w -= step
            if np.abs(step).max() < 1e-9:
                break
        self.a, self.b = float(w[0]), float(w[1])
        return self

    def predict(self, scores):
        return _sigmoid(self.a * self._x(scores) + self.b)

    def llr(self, scores):
        """log-likelihood ratio of 'event' vs 'no event' for each score, prior-free."""
        p = np.clip(self.predict(scores), 1e-9, 1 - 1e-9)
        prior = np.log(self.prevalence / (1 - self.prevalence))
        return np.log(p / (1 - p)) - prior


def ece(p, y, bins=10):
    p, y = np.asarray(p, float), np.asarray(y, float)
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, bins - 1)
    return float(sum((idx == k).mean() * abs(p[idx == k].mean() - y[idx == k].mean()) for k in range(bins) if (idx == k).any()))


class Sprt:
    """Sequential test. update(llr) returns 'alarm', 'clear' or 'continue'.
    alpha = wanted false-alarm probability per scene, beta = wanted miss probability per scene."""

    def __init__(self, alpha=0.001, beta=0.1, floor=None, rho=1.0):
        self.A = float(np.log((1 - beta) / alpha))
        self.B = float(np.log(beta / (1 - alpha)))
        self.floor = self.B if floor is None else floor
        self.rho = rho
        self.s = 0.0
        self.n = 0

    def reset(self):
        self.s, self.n = 0.0, 0

    def update(self, llr):
        self.n += 1
        self.s = max(self.floor, self.s + self.rho * float(llr))
        if self.s >= self.A:
            return "alarm"
        if self.s <= self.B and self.floor <= self.B:
            return "clear"
        return "continue"


def run_scene(llrs, **kw):
    """Feed a sequence; returns (decision, frames used)."""
    t = Sprt(**kw)
    for x in llrs:
        d = t.update(x)
        if d != "continue":
            return d, t.n
    return "continue", t.n
