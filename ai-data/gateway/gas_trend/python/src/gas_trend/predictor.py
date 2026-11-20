"""Run-time class on the gateway: numpy only. Keeps the last scans of one box and returns the onset probability."""
import collections

import numpy as np

from gw_common import load_model
from .data import FEATURES, WINDOW


class TrendPredictor:
    def __init__(self, model_path):
        self.model = load_model(model_path)
        self.thr = float(self.model.meta["threshold"])
        self.horizon = int(self.model.meta.get("horizon", 8))
        self.buf = collections.deque(maxlen=WINDOW)

    def update(self, score, depth, bands, temp_c, rh_pct):
        """One call per received scan result (after the chain's warm-up)."""
        self.buf.append([score, depth, *bands, temp_c, rh_pct])
        if len(self.buf) < WINDOW:
            return dict(p_onset=0.0, early=False, ready=False, horizon_scans=self.horizon)
        x = self.model.standardise(np.array(self.buf))
        p = float(1.0 / (1.0 + np.exp(-self.model.forward(x, standardised=True)[0])))
        return dict(p_onset=p, early=p >= self.thr, ready=True, horizon_scans=self.horizon)
