"""Run-time class on the gateway (numpy only, plus the box engine)."""
import numpy as np

from .ensemble import WeatherEnsemble, run_engine

EFFIS_CLASSES = (5.2, 11.2, 21.3, 38.0, 50.0)          # upper limits of very low, low, moderate, high, very high
HIGH = 21.3


class FwiForecaster:
    def __init__(self, climate, n_members=100, seed=0, quantiles=(0.1, 0.5, 0.9)):
        self.ens = WeatherEnsemble(climate, n_members, seed)
        self.q = quantiles

    def forecast(self, state, today, doy, external=None):
        """`state`: (ffmc, dmc, dc) after today. `today`: dict temp, rh, wind, rain. `doy`: day of year of today.
        `external`: optional list of 1 to 3 (temp, rh, wind, rain) from a weather service; replaces the learned weather (no spread)."""
        if external is not None:
            runs = [run_engine(state, list(external), doy)]
            fw = np.array([[r["fwi"] for r in runs[0]]])
        else:
            w = self.ens.sample(today, doy, 3)
            fw = np.array([[r["fwi"] for r in run_engine(state, [(w["temp"][m, j], w["rh"][m, j], w["wind"][m, j], w["rain"][m, j]) for j in range(3)], doy)]
                           for m in range(self.ens.n)])
        qs = np.quantile(fw, self.q, axis=0)                      # (3 quantiles, 3 days)
        out = []
        for j in range(fw.shape[1]):
            med = float(qs[1, j])
            out.append(dict(day=j + 1, q10=float(qs[0, j]), q50=med, q90=float(qs[2, j]),
                            p_high=float((fw[:, j] >= HIGH).mean()),
                            class_median=int(np.searchsorted(EFFIS_CLASSES, med, side="right"))))
        return out
