"""Method A: weather ensemble, then the box's own FWI engine."""
import numpy as np

from fwi import codes
from gw_common.weather import month_of


def run_engine(state, days, doy0):
    """Advance (ffmc, dmc, dc) over `days` = list of (temp, rh, wind, rain) starting at day-of-year doy0+1. Returns list of dicts incl. 'fwi'."""
    f, p, d = state
    out = []
    for i, (t, rh, w, r) in enumerate(days):
        m = month_of(int(doy0 + 1 + i))
        f = codes.ffmc_daily(f, t, rh, w, r)
        p = codes.dmc(p, t, rh, r, m)
        d = codes.dc(d, t, r, m)
        ii = codes.isi(f, w)
        b = codes.bui(p, d)
        out.append(dict(ffmc=f, dmc=p, dc=d, isi=ii, bui=b, fwi=codes.fwi(ii, b)))
        state = (f, p, d)
    return out


class WeatherEnsemble:
    def __init__(self, climate, n_members=100, seed=0):
        self.c, self.n, self.rng = climate, n_members, np.random.default_rng(seed)

    def sample(self, last, doy0, horizon=3):
        """`last`: dict temp, rh, wind, rain of the origin day. Returns arrays (n, horizon) for temp, rh, wind, rain."""
        c, rng, n = self.c, self.rng, self.n
        out = {k: np.zeros((n, horizon)) for k in ("temp", "rh", "wind", "rain")}
        for k in ("temp", "rh", "wind"):
            a0 = last[k] - c.mean[k][int(doy0)]
            for j in range(horizon):
                L = j  # index into phi/sigma (lead j+1)
                mu = c.phi[k][L] * a0
                # members share a common draw across leads for persistence of the anomaly noise
                out[k][:, j] = c.mean[k][int(doy0) + j + 1 if int(doy0) + j + 1 < 367 else 366] + mu + rng.normal(0, c.sigma[k][L], n)
        wet = np.full(n, last["rain"] >= 0.5)
        for j in range(horizon):
            d = min(int(doy0) + j + 1, 366)
            p = np.where(wet, c.markov["p_ww"], c.markov["p_dw"][d])
            wet = rng.random(n) < p
            amt = rng.gamma(c.gamma["shape"], c.gamma["scale"], n)
            out["rain"][:, j] = np.where(wet, np.maximum(amt, 0.5), 0.0)
            out["temp"][:, j] += np.where(wet, c.wet_shift["temp"], 0.0)
            out["rh"][:, j] += np.where(wet, c.wet_shift["rh"], 0.0)
        out["rh"] = np.clip(out["rh"], 5.0, 100.0)
        out["wind"] = np.clip(out["wind"], 0.0, 80.0)
        return out
