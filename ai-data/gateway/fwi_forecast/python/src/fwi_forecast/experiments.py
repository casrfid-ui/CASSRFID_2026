"""Experiments as functions (notebooks and tests call the same code)."""
import numpy as np

from fwi import codes
from gw_common import block_bootstrap
from gw_common.weather import simulate_years, month_of
from risk_gru.features import fwi_codes
from .climate import Climate
from .ensemble import WeatherEnsemble, run_engine
from .forecaster import HIGH

SPINUP = 30


def seasons(n, seed):
    out = []
    for s in simulate_years(n, seed=seed):
        c = fwi_codes(s["temp"], s["rh"], s["wind"], s["rain"], s["doy"])
        s.update(c)
        out.append(s)
    return out


def origins(season, horizon=3, spinup=SPINUP):
    return range(spinup, len(season["doy"]) - horizon)


def method_A(clim, season, i, n_members=100, rng_seed=0):
    ens = WeatherEnsemble(clim, n_members, seed=rng_seed + i)
    today = {k: season[k][i] for k in ("temp", "rh", "wind", "rain")}
    w = ens.sample(today, season["doy"][i], 3)
    state = (season["ffmc"][i], season["dmc"][i], season["dc"][i])
    fw = np.array([[r["fwi"] for r in run_engine(state, [(w["temp"][m, j], w["rh"][m, j], w["wind"][m, j], w["rain"][m, j]) for j in range(3)], season["doy"][i])]
                   for m in range(n_members)])
    return fw                                                       # (members, 3)


def repeat_today(season, i):
    d = [(season[k][i] for k in ("temp", "rh", "wind", "rain"))]
    day = tuple(float(season[k][i]) for k in ("temp", "rh", "wind", "rain"))
    state = (season["ffmc"][i], season["dmc"][i], season["dc"][i])
    return np.array([r["fwi"] for r in run_engine(state, [day] * 3, season["doy"][i])])


def oracle(season, i):
    days = [tuple(float(season[k][i + j]) for k in ("temp", "rh", "wind", "rain")) for j in (1, 2, 3)]
    state = (season["ffmc"][i], season["dmc"][i], season["dc"][i])
    return np.array([r["fwi"] for r in run_engine(state, days, season["doy"][i])])


def features_B(season, i, clim):
    d = int(season["doy"][i])
    f = [season["fwi"][i], season["fwi"][i - 1], season["fwi"][i - 2], season["ffmc"][i], season["dmc"][i], season["dc"][i],
         season["temp"][i], season["rh"][i], season["wind"][i], season["rain"][i],
         season["temp"][i] - clim.mean["temp"][d], season["rh"][i] - clim.mean["rh"][d], season["wind"][i] - clim.mean["wind"][d],
         np.sin(2 * np.pi * month_of(d) / 12), np.cos(2 * np.pi * month_of(d) / 12)]
    return f


def stack(seasons_, clim, n_members=0, members=100, with_A=False, seed=0):
    X, Y, blk, pers, rep = [], [], [], [], []
    A = []
    for si, s in enumerate(seasons_):
        for i in origins(s):
            X.append(features_B(s, i, clim)); Y.append(s["fwi"][i + 1:i + 4]); blk.append(si * 100 + i // 7)
            pers.append([s["fwi"][i]] * 3); rep.append(repeat_today(s, i))
            if with_A:
                A.append(method_A(clim, s, i, members, seed))
    out = dict(X=np.array(X), Y=np.array(Y), blocks=np.array(blk), persistence=np.array(pers), repeat=np.array(rep))
    if with_A:
        A = np.array(A)                                              # (N, members, 3)
        out.update(A_q=np.quantile(A, [0.1, 0.5, 0.9], axis=1).transpose(1, 0, 2), A_phigh=(A >= HIGH).mean(1))
    return out


def fit_B(Xtr, Ytr, seed=0):
    from sklearn.ensemble import HistGradientBoostingRegressor as H
    models = {}
    for h in range(3):
        for q in (0.1, 0.5, 0.9):
            models[(h, q)] = H(loss="quantile", quantile=q, max_depth=3, learning_rate=0.05, max_iter=200, random_state=seed).fit(Xtr, Ytr[:, h])
    return models


def predict_B(models, X):
    return np.stack([[models[(h, q)].predict(X) for q in (0.1, 0.5, 0.9)] for h in range(3)]).transpose(2, 1, 0)   # (N, 3q, 3h)


def mae_row(pred, Y, blocks, nboot=300):
    """MAE per horizon with block-bootstrap CI: [(mae, lo, hi)] x 3."""
    out = []
    for h in range(3):
        e = np.abs(pred[:, h] - Y[:, h])
        f = lambda y, s: float(s.mean())
        out.append(block_bootstrap(f, np.zeros_like(e), e, blocks, nboot, seed=3))
    return out


def coverage(q, Y):
    return [float(((Y[:, h] >= q[:, 0, h]) & (Y[:, h] <= q[:, 2, h])).mean()) for h in range(3)]


def engine_vs_published(tables):
    """Max and mean absolute difference between our engine (run from the standard start values) and the published codes, after 20 days."""
    res = {}
    for t in tables:
        c = fwi_codes(t["temp"], t["rh"], t["wind"], t["rain"], t["doy"])
        for k in ("ffmc", "dmc", "dc", "isi", "bui", "fwi"):
            d = np.abs(c[k][20:] - t[k][20:])
            res[(t["group"][0], k)] = (float(d.mean()), float(d.max()))
    return res


def algerian_check(path, members=100, seed=0, own_engine=False):
    """Leave-one-site-out. `own_engine=False`: state = published codes, truth = published FWI. Climate = one mean per variable from the other site. State at origin = the published codes. Truth = published FWI."""
    from risk_gru import datasets
    tabs = datasets.algerian(path)
    if own_engine:          # state and truth both from OUR engine run on the real weather (the published codes come from another implementation)
        for t in tabs:
            t.update(fwi_codes(t["temp"], t["rh"], t["wind"], t["rain"], t["doy"]))
    res = {}
    for k, t in enumerate(tabs):
        other = tabs[1 - k]
        clim = Climate.constant([other])
        P, Rp, A, Y, blk = [], [], [], [], []
        for i in range(3, len(t["doy"]) - 3):
            Y.append(t["fwi"][i + 1:i + 4]); blk.append(i // 7)
            P.append([t["fwi"][i]] * 3); Rp.append(repeat_today(t, i))
            A.append(method_A(clim, t, i, members, seed))
        A = np.array(A)
        q = np.quantile(A, [0.1, 0.5, 0.9], axis=1).transpose(1, 0, 2)
        res[t["group"][0]] = dict(Y=np.array(Y), blocks=np.array(blk), persistence=np.array(P), repeat=np.array(Rp), A_q=q)
    return res
