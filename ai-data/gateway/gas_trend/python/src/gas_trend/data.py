"""From recordings to training examples.

One recording ("episode") = one sensor during one burn. The box's gas chain is replayed scan by scan; what the gateway receives per
scan is (score, depth, 3 band values, temp, rh). A window = the last WINDOW scans. Target = 1 when the first response phase
(phase 2, the first phase with a response in this data set) starts within the next H scans; scans after the onset are excluded."""
import numpy as np

from gas_chain import GasChain, Config
from gas_chain.config import SMOKE

FEATURES = ("score", "depth", "band1", "band2", "band3", "temp_c", "rh_pct")
WINDOW = 12
H_DEFAULT = 8
ONSET_PHASE = 2


def chain_features(data):
    """Replay one fresh chain per episode. Returns dict of arrays (one row per scan): X (n,7), cls, warmup, t (s since the episode start), plus ids."""
    n = len(data["episode"])
    X = np.zeros((n, len(FEATURES))); cls = np.zeros(n, int); warm = np.zeros(n, bool)
    chain, last = None, None
    for i in range(n):
        if data["episode"][i] != last:
            chain, last = GasChain(Config()), data["episode"][i]
        r = chain.update(data["gas"][i], data["temp"][i], data["rh"][i], data["dt"][i])
        X[i] = [r.score, r.depth, *r.bands, float(np.mean(data["temp"][i])), float(np.mean(data["rh"][i]))]
        cls[i], warm[i] = r.cls, r.warmup
    t = np.zeros(n)
    for ep in np.unique(data["episode"]):
        m = np.where(data["episode"] == ep)[0]
        t[m] = np.cumsum(data["dt"][m])
    return dict(X=X, cls=cls, warmup=warm, t=t, episode=data["episode"], phase=data["phase"], node=data["node"],
                experiment=data["experiment"], dt=data["dt"])


def build_samples(f, window=WINDOW, horizon=H_DEFAULT):
    """Windows ending at every post-warm-up scan that precedes the onset. Returns X (N, window, 7) and a meta dict
    (y, episode, node, phase, t, dt, chain_smoke, idx = row index in `f`)."""
    X, rows = [], []
    for ep in np.unique(f["episode"]):
        idx = np.where(f["episode"] == ep)[0]
        ph = f["phase"][idx]
        on = np.where(ph >= ONSET_PHASE)[0]
        if len(on) == 0:
            continue
        onset = on[0]                                         # position (in the episode) of the first response scan
        for k in range(onset):
            if f["warmup"][idx[k]] or k < window - 1:
                continue
            X.append(f["X"][idx[k - window + 1:k + 1]])
            rows.append((int(onset - k <= horizon), ep, f["node"][idx[k]], ph[k], f["t"][idx[k]], f["dt"][idx[k]], idx[k]))
    r = np.array(rows)
    meta = dict(y=r[:, 0].astype(float), episode=r[:, 1].astype(int), node=r[:, 2].astype(int), phase=r[:, 3].astype(int),
                t=r[:, 4], dt=r[:, 5], idx=r[:, 6].astype(int))
    return np.array(X), meta


def onset_alarm_times(f):
    """Per episode: (t_onset, t_chain_alarm or nan, t_warmup_end). Chain alarm = first scan at/after the onset with class SMOKE."""
    out = {}
    for ep in np.unique(f["episode"]):
        idx = np.where(f["episode"] == ep)[0]
        ph = f["phase"][idx]
        on = np.where(ph >= ONSET_PHASE)[0]
        if len(on) == 0:
            continue
        sm = np.where((f["cls"][idx] == SMOKE) & (np.arange(len(idx)) >= on[0]))[0]
        w = np.where(~f["warmup"][idx])[0]
        out[int(ep)] = dict(t_onset=float(f["t"][idx[on[0]]]), t_alarm=float(f["t"][idx[sm[0]]]) if len(sm) else float("nan"),
                            t_warm=float(f["t"][idx[w[0]]]) if len(w) else float("nan"), node=int(f["node"][idx[0]]))
    return out
