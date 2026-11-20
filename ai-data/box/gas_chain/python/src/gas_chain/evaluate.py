"""Replay of a data set through the gas chain, and the metrics used by the fiche."""
import numpy as np

from .chain import GasChain
from .config import FAULT, NORMAL, SMOKE, Config

STRONG_PHASES = (3, 4, 5)       # strong smoke (see data_mendeley)


def dilute(data, factor, keep_noise=True, seed=0):
    """Semi-synthetic distance proxy: scale the part of ln R added by the fire. 1 = as recorded.

    The reference is the median ln R of the clean start (phase 0) of each episode and heater step.
    The sensor's own noise does not shrink with distance: with `keep_noise`, white noise is added back so that
    the noise level stays that of the clean start (scan-to-scan noise per step, drift removed). Real dilution is not linear and a
    distant node would see other gases: this is a stand-in only."""
    rng = np.random.default_rng(seed)
    out = {k: v.copy() if isinstance(v, np.ndarray) else v for k, v in data.items()}
    ln = np.log(data["gas"])
    for ep in np.unique(data["episode"]):
        m = data["episode"] == ep
        clean = m & (data["phase"] == 0)
        ref = np.median(ln[clean], axis=0)
        diluted = ref + factor * (ln[m] - ref)
        if keep_noise and factor < 1.0:
            sigma = np.diff(ln[clean], axis=0).std(axis=0) / np.sqrt(2.0)   # scan-to-scan noise, drift removed
            diluted = diluted + rng.normal(0.0, 1.0, diluted.shape) * sigma * np.sqrt(1.0 - factor ** 2)
        out["gas"][m] = np.exp(diluted)
    return out


def replay(data, cfg=None):
    """Run one fresh chain per episode. Returns arrays of score, cls, faults, warmup (one row per scan)."""
    n = len(data["episode"])
    res = dict(score=np.zeros(n), cls=np.zeros(n, int), faults=np.zeros(n, int), warmup=np.zeros(n, bool))
    chain, last_ep = None, None
    for i in range(n):
        if data["episode"][i] != last_ep:
            chain, last_ep = GasChain(cfg or Config()), data["episode"][i]
        r = chain.update(data["gas"][i], data["temp"][i], data["rh"][i], data["dt"][i])
        res["score"][i], res["cls"][i], res["faults"][i], res["warmup"][i] = r.score, r.cls, r.faults, r.warmup
    return res


def _rate(mask, flag):
    return float(flag[mask].mean()) if mask.any() else float("nan")


def metrics(data, res, experiment=None, start_phase=1):
    """False smoke on clean air, recall and fault share in strong smoke, delay to first smoke (per episode).

    The delay is counted from the first scan of `start_phase` (1 = burn tagged, 2 = first phase with a response)."""
    sel = np.ones(len(data["phase"]), bool) if experiment is None else data["experiment"] == experiment
    live = sel & ~res["warmup"]
    smoke = res["cls"] == SMOKE
    clean = live & (data["phase"] == 0)
    strong = live & np.isin(data["phase"], STRONG_PHASES)
    delays, missed = [], 0
    for ep in np.unique(data["episode"][sel]):
        m = (data["episode"] == ep) & ~res["warmup"]
        burn = m & (data["phase"] >= start_phase)
        if not burn.any():
            continue
        t = np.cumsum(data["dt"][data["episode"] == ep])
        t = t[~res["warmup"][data["episode"] == ep]]
        ph = data["phase"][m]
        hits = np.flatnonzero(smoke[m] & (ph >= 1))
        if len(hits) == 0:
            missed += 1
            continue
        start = np.flatnonzero(ph >= start_phase)[0]
        delays.append(float(t[hits[0]] - t[start]))
    return dict(
        scans=int(sel.sum()), clean_scans=int(clean.sum()), strong_scans=int(strong.sum()),
        false_smoke_clean=_rate(clean, smoke), recall_strong=_rate(strong, smoke),
        fault_in_strong=_rate(strong, res["cls"] == FAULT), episodes_never_called=missed,
        delay_min_median=float(np.median(delays) / 60) if delays else float("nan"),
    )


def fit_compensation(data, mask):
    """Least-squares a_t (ln R per degC) and b_h (ln R per % RH) on the scans selected by `mask` (clean air only).

    ln R, T and RH are centred per episode and heater step, so only the co-movement inside one run counts.
    Returns (a_t, b_h, r2)."""
    ln = np.log(data["gas"])
    y, t, h = [], [], []
    for ep in np.unique(data["episode"][mask]):
        m = mask & (data["episode"] == ep)
        if m.sum() < 5:
            continue
        y.append((ln[m] - ln[m].mean(axis=0)).ravel())
        t.append((data["temp"][m] - data["temp"][m].mean(axis=0)).ravel())
        h.append((data["rh"][m] - data["rh"][m].mean(axis=0)).ravel())
    y, X = np.concatenate(y), np.column_stack([np.concatenate(t), np.concatenate(h)])
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    r2 = 1.0 - ((y - X @ coef) ** 2).sum() / (y ** 2).sum()
    return float(coef[0]), float(coef[1]), float(r2)


def response_depth(data, bands=Config().bands):
    """Drop of ln R against the clean start of the same episode: max over the bands of the band mean.

    This is the physical size of the response, whatever the chain says. Used as an amplitude-aware truth."""
    ln = np.log(data["gas"])
    out = np.zeros(len(ln))
    for ep in np.unique(data["episode"]):
        m = data["episode"] == ep
        ref = np.median(ln[m & (data["phase"] == 0)], axis=0)
        drop = ref - ln[m]
        out[m] = np.max([drop[:, a:b].mean(axis=1) for a, b in bands], axis=0)
    return out


def recall_detectable(data, res, min_response_ln):
    """Recall among strong-phase scans whose physical response is at least `min_response_ln`."""
    mask = (~res["warmup"]) & np.isin(data["phase"], STRONG_PHASES) & (response_depth(data) >= min_response_ln)
    return _rate(mask, res["cls"] == SMOKE), int(mask.sum())
