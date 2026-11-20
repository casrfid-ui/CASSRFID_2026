"""The experiments of the notebook and of the tests, as functions (so that notebook and tests run the same code)."""
import numpy as np

from gw_common import auc, average_precision, block_bootstrap, brier, paired_block_bootstrap
from . import datasets, features
from .baselines import Baselines
from .train import calibrate, calibrated, fit_gru, thresholds

MODELS = ("persistence", "fwi_threshold", "lr_cur", "lr_win", "gbm", "gru")


def subset(X, Y, meta, mask):
    return X[mask], Y[mask], {k: v[mask] for k, v in meta.items()}


def split_by_group(tables, n_train, n_val):
    """Seasons are ordered; train = first n_train, validation = next n_val, test = the rest. Never shared (unit-tested)."""
    return tables[:n_train], tables[n_train:n_train + n_val], tables[n_train + n_val:]


def run_synthetic(n_years=200, seed=0, gru_seeds=5, epochs=80, verbose=False, variant="additive"):
    tables = datasets.synthetic(n_years, seed=seed, variant=variant)
    tr, va, te = split_by_group(tables, int(0.6 * n_years), int(0.15 * n_years))
    Xtr, Ytr, mtr = features.build_windows(tr)
    Xva, Yva, mva = features.build_windows(va)
    Xte, Yte, mte = features.build_windows(te)
    base = Baselines(seed).fit(Xtr, Ytr, mtr)
    scores = base.scores(Xte, mte)
    grus, hist = [], []
    for s in range(gru_seeds):
        m, h = fit_gru(Xtr, Ytr, Xva, Yva, seed=s, epochs=epochs, verbose=verbose)
        grus.append(m); hist.append(h)
    best = int(np.argmax([h["best_val_ap"] for h in hist]))
    model = grus[best]
    scores["gru"] = model.predict_proba(Xte, standardised=False)
    scores["gru_seeds"] = np.stack([g.predict_proba(Xte, standardised=False) for g in grus])     # (seeds, N, 3)
    scores["oracle"] = mte["p_true"]
    calib = calibrate(model, Xva, Yva)
    thr = thresholds(model, calib, Xva, Yva)
    return dict(tables=(tr, va, te), data=((Xtr, Ytr, mtr), (Xva, Yva, mva), (Xte, Yte, mte)), scores=scores, model=model,
                calib=calib, thr=thr, hist=hist, best_seed=best)


def table(scores, Y, blocks, names=MODELS + ("oracle",), nboot=300):
    """Rows: (model, horizon, auroc, lo, hi, ap, ap_lo, ap_hi, brier)."""
    rows = []
    for n in names:
        if n not in scores:
            continue
        for h in range(Y.shape[1]):
            y, s = Y[:, h], scores[n][:, h]
            a = block_bootstrap(auc, y, s, blocks, nboot, seed=1)
            p = block_bootstrap(average_precision, y, s, blocks, nboot, seed=2)
            b = brier(y, np.clip(s, 0, 1)) if n in ("lr_cur", "lr_win", "gbm", "gru", "oracle") else float("nan")
            rows.append((n, h + 1, *a, *p, b))
    return rows


def run_algerian(path, gru_seeds=5, epochs=60):
    """Leave-one-site-out in both directions. Validation = the last 25 % of the training site (time order)."""
    tabs = datasets.algerian(path)
    out = {}
    for k, test_site in enumerate(("Bejaia", "SidiBelAbbes")):
        te = [t for t in tabs if t["group"][0] == test_site]
        trn = [t for t in tabs if t["group"][0] != test_site]
        Xa, Ya, ma = features.build_windows(trn)
        cut = int(0.75 * len(Xa))
        Xtr, Ytr, mtr = Xa[:cut], Ya[:cut], {kk: v[:cut] for kk, v in ma.items()}
        Xva, Yva = Xa[cut:], Ya[cut:]
        Xte, Yte, mte = features.build_windows(te)
        base = Baselines(0).fit(Xtr, Ytr, mtr)
        sc = base.scores(Xte, mte)
        ms = []
        for s in range(gru_seeds):
            m, _ = fit_gru(Xtr, Ytr, Xva, Yva, seed=s, epochs=epochs, patience=8)
            ms.append(m.predict_proba(Xte, standardised=False))
        sc["gru"] = np.mean(ms, 0)                        # average of the seeds: the model, not one lucky seed
        sc["gru_seeds"] = np.stack(ms)
        out[test_site] = dict(Y=Yte, meta=mte, scores=sc, n_train=len(Xtr), n_val=len(Xva))
    return out
