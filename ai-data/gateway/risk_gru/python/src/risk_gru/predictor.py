"""Run-time side on the gateway: numpy only (no torch). One call per day per box."""
import collections
import math

import numpy as np

from gw_common import load_model
from .features import FEATURES, HORIZONS, WINDOW


class RiskPredictor:
    """Keeps the last WINDOW days of one box and answers with the calibrated risk of fire for the next 3 days.

    `model_path`: .npz written by `train.save_deployable` (weights, standardisation, calibration, thresholds, provenance)."""

    def __init__(self, model_path):
        self.model = load_model(model_path)
        meta = self.model.meta
        self.calib = meta["calibration"]                  # [{"a":..,"b":..} per horizon]
        self.thr = meta["thresholds"]                     # {"moderate":..,"high":..} on max over horizons
        self.provenance = meta.get("provenance", "unknown")
        self.window = collections.deque(maxlen=WINDOW)
        self.missing = 0

    @staticmethod
    def row_of(day):
        m = int(day["month"])
        d = dict(day)
        d["sin_month"], d["cos_month"] = math.sin(2 * math.pi * m / 12), math.cos(2 * math.pi * m / 12)
        return np.array([float(d[k]) for k in FEATURES])

    def update(self, day=None):
        """`day`: dict with temp, rh, wind, rain, ffmc, dmc, dc, isi, bui, fwi, month. `None` = no frame today: the last day is repeated and counted."""
        if day is None:
            if not self.window:
                raise ValueError("no data yet")
            self.window.append(self.window[-1])
            self.missing += 1
        else:
            self.window.append(self.row_of(day))
        provisional = len(self.window) < WINDOW
        rows = list(self.window)
        while len(rows) < WINDOW:                         # short history: the first day is repeated at the front
            rows.insert(0, rows[0])
        x = self.model.standardise(np.array(rows))
        logits = self.model.forward(x, standardised=True)
        p = [1.0 / (1.0 + math.exp(-(c["a"] * _logit_of(1.0 / (1.0 + math.exp(-lg))) + c["b"]))) for lg, c in zip(logits, self.calib)]
        pm = max(p)
        level = "high" if pm >= self.thr["high"] else "moderate" if pm >= self.thr["moderate"] else "low"
        return {"p_day1": p[0], "p_day2": p[1], "p_day3": p[2], "level": level, "provisional": provisional,
                "missing_days": self.missing, "model": self.provenance}


def _logit_of(s, eps=1e-4):
    s = min(max(s, eps), 1 - eps)
    return math.log(s / (1 - s))
