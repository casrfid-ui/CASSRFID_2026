"""Learned statistics of the local weather: seasonal means, how anomalies fade with the lead time, how rain behaves.

Everything here is estimated from a training record (several seasons of noon values at the site). Nothing is assumed
about the generator that makes the synthetic data; the method only assumes (i) a smooth seasonal cycle, (ii) anomalies that
decay with the lead time (AR-like), (iii) rain as a two-state chain with gamma amounts, (iv) wet days shifting T and RH."""
import json

import numpy as np

VARS = ("temp", "rh", "wind")
LEADS = (1, 2, 3)


def _smooth_by_doy(doy, x, half=10):
    out = np.full(367, np.nan)
    for d in range(1, 367):
        m = np.abs(((doy - d + 183) % 366) - 183) <= half
        if m.sum() >= 5:
            out[d] = x[m].mean()
    idx = np.arange(367)
    ok = ~np.isnan(out)
    return np.interp(idx, idx[ok], out[ok])


class Climate:
    def __init__(self, mean=None, phi=None, sigma=None, wet_shift=None, markov=None, gamma=None, doy_lo=1, doy_hi=366):
        self.mean, self.phi, self.sigma = mean, phi, sigma          # mean[var] (367,), phi[var][lead], sigma[var][lead]
        self.wet_shift, self.markov, self.gamma = wet_shift, markov, gamma
        self.doy_lo, self.doy_hi = doy_lo, doy_hi

    @classmethod
    def fit(cls, seasons):
        """`seasons`: list of dicts with doy, temp, rh, wind, rain (one per site-season, daily)."""
        doy = np.concatenate([s["doy"] for s in seasons])
        cat = {k: np.concatenate([s[k] for s in seasons]) for k in VARS + ("rain",)}
        mean = {k: _smooth_by_doy(doy, cat[k]) for k in VARS}
        phi, sigma = {}, {}
        for k in VARS:
            an = [s[k] - mean[k][s["doy"]] for s in seasons]
            phi[k], sigma[k] = [], []
            for L in LEADS:
                a0 = np.concatenate([x[:-L] for x in an])
                aL = np.concatenate([x[L:] for x in an])
                b = float((a0 * aL).sum() / max((a0 * a0).sum(), 1e-9))        # regression through the origin
                phi[k].append(b)
                sigma[k].append(float(np.std(aL - b * a0)))
        wet = cat["rain"] >= 0.5
        wet_shift = {}
        for k in ("temp", "rh"):
            an = np.concatenate([s[k] - mean[k][s["doy"]] for s in seasons])
            wet_shift[k] = float(an[wet].mean() - an[~wet].mean()) if wet.any() else 0.0
        # rain chain by calendar month of the season (3 classes of doy are enough for a 7-month season)
        w2 = [(s["doy"][1:], s["rain"][:-1] >= 0.5, s["rain"][1:] >= 0.5) for s in seasons]
        d2 = np.concatenate([a for a, _, _ in w2]); prev = np.concatenate([b for _, b, _ in w2]); cur = np.concatenate([c for _, _, c in w2])
        grid = np.arange(367)
        p_dw = _smooth_by_doy(d2[~prev], cur[~prev].astype(float), half=20) if (~prev).sum() > 20 else np.full(367, 0.1)
        p_ww = float(cur[prev].mean()) if prev.sum() > 5 else 0.4
        amt = cat["rain"][wet]
        m, v = (amt.mean(), amt.var()) if wet.sum() > 5 else (5.0, 50.0)
        gamma = dict(shape=float(m * m / max(v, 1e-6)), scale=float(max(v, 1e-6) / m))
        c = cls(mean, phi, sigma, wet_shift, dict(p_dw=p_dw, p_ww=p_ww), gamma, int(doy.min()), int(doy.max()))
        return c

    def to_json(self):
        f = lambda a: [float(x) for x in a]
        return json.dumps(dict(mean={k: f(v) for k, v in self.mean.items()}, phi=self.phi, sigma=self.sigma,
                               wet_shift=self.wet_shift, markov=dict(p_dw=f(self.markov["p_dw"]), p_ww=self.markov["p_ww"]),
                               gamma=self.gamma, doy_lo=self.doy_lo, doy_hi=self.doy_hi))

    @classmethod
    def from_json(cls, s):
        d = json.loads(s)
        d["mean"] = {k: np.array(v) for k, v in d["mean"].items()}
        d["markov"]["p_dw"] = np.array(d["markov"]["p_dw"])
        return cls(**d)

    @classmethod
    def constant(cls, seasons):
        """For tiny records (Algerian check): one mean per variable instead of a seasonal curve."""
        c = cls.fit(seasons)
        for k in VARS:
            allv = np.concatenate([s[k] for s in seasons])
            c.mean[k] = np.full(367, allv.mean())
        return c
