"""From daily weather to model inputs.

One *season table* = one site-year: arrays of equal length, one value per day (noon): doy, temp, rh, wind, rain, the six FWI codes,
the label `fire` (0/1) and ids (`group` = year or site, `week` = block for the bootstrap).
A *window* is the last WINDOW days up to day t; the targets are the labels at t+1, t+2, t+3."""
import numpy as np

from fwi import codes
from gw_common.weather import month_of

WINDOW = 14
HORIZONS = (1, 2, 3)
RAW = ("temp", "rh", "wind", "rain")
CODES = ("ffmc", "dmc", "dc", "isi", "bui", "fwi")
FEATURES = RAW + CODES + ("sin_month", "cos_month")      # 12 inputs
SPINUP = 30                                             # days at the start of a season where the codes are not yet reliable


def fwi_codes(temp, rh, wind, rain, doy, start=(85.0, 6.0, 15.0)):
    """The box engine's daily chain over a season. Returns dict of arrays."""
    f, p, d = start
    out = {k: np.zeros(len(temp)) for k in CODES}
    for i in range(len(temp)):
        m = month_of(int(doy[i]))
        f = codes.ffmc_daily(f, temp[i], rh[i], wind[i], rain[i])
        p = codes.dmc(p, temp[i], rh[i], rain[i], m)
        d = codes.dc(d, temp[i], rain[i], m)
        i_ = codes.isi(f, wind[i])
        b = codes.bui(p, d)
        for k, v in zip(CODES, (f, p, d, i_, b, codes.fwi(i_, b))):
            out[k][i] = v
    return out


def season_table(doy, temp, rh, wind, rain, fire, group, codes_given=None):
    """Assemble a season table. `codes_given`: dict of the six published codes (used for the Algerian data set); otherwise computed."""
    doy = np.asarray(doy, int)
    c = codes_given if codes_given is not None else fwi_codes(temp, rh, wind, rain, doy)
    month = np.array([month_of(int(x)) for x in doy])
    t = dict(doy=doy, temp=np.asarray(temp, float), rh=np.asarray(rh, float), wind=np.asarray(wind, float),
             rain=np.asarray(rain, float), fire=np.asarray(fire, float), group=np.full(len(doy), group),
             week=(np.arange(len(doy)) // 7), sin_month=np.sin(2 * np.pi * month / 12), cos_month=np.cos(2 * np.pi * month / 12))
    t.update({k: np.asarray(c[k], float) for k in CODES})
    return t


def matrix(table):
    return np.stack([table[k] for k in FEATURES], 1)


def build_windows(tables, window=WINDOW, horizons=HORIZONS, spinup=SPINUP):
    """Stack windows of several season tables. Returns X (N, window, 12), Y (N, len(horizons)), meta dict (group, week, fwi, fire_today)."""
    X, Y, G, W, F, T, P = [], [], [], [], [], [], []
    for t in tables:
        M = matrix(t)
        n = len(M)
        lo = max(window - 1, spinup)
        for i in range(lo, n - max(horizons)):
            y_row = [t["fire"][i + h] for h in horizons]
            if np.isnan(y_row).any() or np.isnan(t["fire"][i]):
                continue                                  # unlabeled day (Algerian data set): the window is not used
            X.append(M[i - window + 1:i + 1])
            Y.append(y_row)
            if "p_true" in t:
                P.append([t["p_true"][i + h] for h in horizons])
            G.append(t["group"][i]); W.append(f'{t["group"][i]}_{t["week"][i]}'); F.append(t["fwi"][i]); T.append(t["fire"][i])
    meta = dict(group=np.array(G), block=np.array(W), fwi=np.array(F), fire_today=np.array(T))
    if P:
        meta["p_true"] = np.array(P)
    return np.array(X), np.array(Y), meta
