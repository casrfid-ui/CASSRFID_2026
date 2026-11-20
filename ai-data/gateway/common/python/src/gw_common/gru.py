"""Numpy GRU classifier in the PyTorch weight layout. The gateway runs this; training happens with torch on a PC.

PyTorch gate order in weight_ih / weight_hh is (reset, update, new):
  r = sigmoid(W_ir x + b_ir + W_hr h + b_hr)
  z = sigmoid(W_iz x + b_iz + W_hz h + b_hz)
  n = tanh(W_in x + b_in + r * (W_hn h + b_hn))
  h' = (1 - z) * n + z * h
"""
import json

import numpy as np


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


class GRUModel:
    """One GRU layer + one linear head. `forward` takes standardised inputs (T, I) or (B, T, I) and returns logits."""

    def __init__(self, w_ih, w_hh, b_ih, b_hh, head_w, head_b, mean=None, std=None, meta=None):
        self.w_ih, self.w_hh = np.asarray(w_ih, np.float64), np.asarray(w_hh, np.float64)
        self.b_ih, self.b_hh = np.asarray(b_ih, np.float64), np.asarray(b_hh, np.float64)
        self.head_w, self.head_b = np.asarray(head_w, np.float64), np.asarray(head_b, np.float64)
        self.hidden = self.w_hh.shape[1]
        self.n_in = self.w_ih.shape[1]
        self.mean = np.zeros(self.n_in) if mean is None else np.asarray(mean, np.float64)
        self.std = np.ones(self.n_in) if std is None else np.asarray(std, np.float64)
        self.meta = meta or {}

    def n_params(self):
        return int(self.w_ih.size + self.w_hh.size + self.b_ih.size + self.b_hh.size + self.head_w.size + self.head_b.size)

    def standardise(self, x):
        return (np.asarray(x, np.float64) - self.mean) / self.std

    def hidden_states(self, xs):
        """xs: (B, T, I) standardised. Returns (B, T, H)."""
        B, T, _ = xs.shape
        H = self.hidden
        h = np.zeros((B, H))
        out = np.zeros((B, T, H))
        for t in range(T):
            gi = xs[:, t] @ self.w_ih.T + self.b_ih
            gh = h @ self.w_hh.T + self.b_hh
            r = _sigmoid(gi[:, :H] + gh[:, :H])
            z = _sigmoid(gi[:, H:2 * H] + gh[:, H:2 * H])
            n = np.tanh(gi[:, 2 * H:] + r * gh[:, 2 * H:])
            h = (1 - z) * n + z * h
            out[:, t] = h
        return out

    def forward(self, xs, standardised=True):
        xs = np.asarray(xs, np.float64)
        single = xs.ndim == 2
        if single:
            xs = xs[None]
        if not standardised:
            xs = self.standardise(xs)
        h = self.hidden_states(xs)[:, -1]
        logits = h @ self.head_w.T + self.head_b
        return logits[0] if single else logits

    def predict_proba(self, xs, standardised=True):
        return _sigmoid(self.forward(xs, standardised))


def save_model(path, model, **extra_meta):
    meta = dict(model.meta)
    meta.update(extra_meta)
    np.savez(path, w_ih=model.w_ih, w_hh=model.w_hh, b_ih=model.b_ih, b_hh=model.b_hh, head_w=model.head_w,
             head_b=model.head_b, mean=model.mean, std=model.std, meta=json.dumps(meta))


def load_model(path):
    z = np.load(path, allow_pickle=False)
    meta = json.loads(str(z["meta"]))
    return GRUModel(z["w_ih"], z["w_hh"], z["b_ih"], z["b_hh"], z["head_w"], z["head_b"], z["mean"], z["std"], meta)
