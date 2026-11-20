"""Leave-one-node-out experiments (the same functions are used by the notebooks and the tests)."""
import numpy as np

from gas_chain import data_mendeley as D
from gas_chain.evaluate import dilute
from gas_chain.config import SMOKE
from gw_common import average_precision, auc, block_bootstrap
from .data import chain_features, build_samples, onset_alarm_times, H_DEFAULT, WINDOW

NODES = (1, 2, 3, 4, 5)
MODELS = ("chain_depth", "slope_rule", "logistic", "gru")


def window_features(X):
    """Hand-made features for the logistic model: last scan, window mean, change over the last 6 scans (per variable)."""
    last = X[:, -1]
    return np.concatenate([last, X.mean(1), X[:, -1] - X[:, -7]], 1)


def slope_score(X, H):
    d = X[:, -6:, 1]
    k = np.arange(6) - 2.5
    slope = (d * k).sum(1) / (k ** 2).sum()
    return d[:, -1] + H * slope


def val_node(test):
    return NODES[(NODES.index(test)) % len(NODES) - 1] if False else NODES[(test) % len(NODES)]


def split(meta, test):
    v = NODES[test % len(NODES)]            # next node (cyclic) is the validation node
    tr = ~np.isin(meta["node"], (test, v))
    return tr, meta["node"] == v, meta["node"] == test


def threshold_for_budget(score, clean_mask, hours, budget_per_hour):
    """Smallest threshold whose flags on clean-air scans stay within budget_per_hour (flag = score >= thr)."""
    s = np.sort(score[clean_mask])[::-1]
    allowed = int(np.floor(budget_per_hour * hours))
    if allowed >= len(s):
        return float(s[-1]) if len(s) else 0.0
    return float(np.nextafter(s[allowed], np.inf))


def clean_hours(meta, mask):
    return float(meta["dt"][mask & (meta["phase"] == 0)].sum() / 3600.0)


def run_factor(factor, data, H=H_DEFAULT, gru_seeds=2, epochs=40, hidden=12, verbose=False):
    d = dilute(data, factor) if factor < 1.0 else data
    f = chain_features(d)
    X, meta = build_samples(f, WINDOW, H)
    alarms = onset_alarm_times(f)
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from gw_common.train_gru import fit_gru
    res = {}
    for test in NODES:
        tr, va, te = split(meta, test)
        # chain false-smoke budget measured on the validation node's clean air
        chain_flag = f["cls"][meta["idx"]] == SMOKE
        h_va, h_te = clean_hours(meta, va), clean_hours(meta, te)
        budget = (chain_flag[va & (meta["phase"] == 0)].sum()) / max(h_va, 1e-9)
        budget_te = (chain_flag[te & (meta["phase"] == 0)].sum()) / max(h_te, 1e-9)
        scores = {"chain_depth": X[:, -1, 1], "slope_rule": slope_score(X, H)}
        W = window_features(X); sc = StandardScaler().fit(W[tr])
        lr = LogisticRegression(C=1.0, max_iter=500, class_weight="balanced").fit(sc.transform(W[tr]), meta["y"][tr])
        scores["logistic"] = lr.decision_function(sc.transform(W))
        best = None
        for s in range(gru_seeds):
            m, h = fit_gru(X[tr], meta["y"][tr][:, None], X[va], meta["y"][va][:, None], seed=s, hidden=hidden, epochs=epochs, patience=8,
                           meta=dict(features=["score", "depth", "band1", "band2", "band3", "temp_c", "rh_pct"], horizon=H))
            if best is None or h["best_val_ap"] > best[1]["best_val_ap"]:
                best = (m, h)
        gm = best[0]
        scores["gru"] = gm.forward(X, standardised=False)[:, 0]
        out = {}
        for name, sco in scores.items():
            thr = threshold_for_budget(sco, va & (meta["phase"] == 0), h_va, budget)
            flag = sco >= thr
            fa_hour = float(flag[te & (meta["phase"] == 0)].sum() / max(h_te, 1e-9))
            leads, missed = {}, 0
            for ep in np.unique(meta["episode"][te]):
                m_ep = te & (meta["episode"] == ep) & (meta["phase"] >= 1)
                a = alarms[int(ep)]
                fl = np.where(flag & m_ep)[0]
                if np.isnan(a["t_alarm"]):
                    continue
                if len(fl):
                    leads[int(ep)] = a["t_alarm"] - meta["t"][fl[0]]
                else:
                    leads[int(ep)] = 0.0
                    missed += 1
            out[name] = dict(thr=thr, fa_per_hour=fa_hour, chain_fa_per_hour=budget_te, leads=leads, missed=missed,
                             ap=average_precision(meta["y"][te], sco[te]), auc=auc(meta["y"][te], sco[te]))
        res[test] = dict(out=out, model=gm, n_train=int(tr.sum()), n_val=int(va.sum()), n_test=int(te.sum()))
        if verbose:
            print("node", test, {k: (round(v["fa_per_hour"], 1), round(float(np.median(list(v["leads"].values()))), 0) if v["leads"] else None) for k, v in out.items()})
    return dict(res=res, alarms=alarms, meta=meta, f=f, X=X)


def lead_summary(run, model, nboot=2000, seed=0):
    """Median lead (s) over episodes with a chain alarm (missed = 0) and its bootstrap CI (blocks = recording = node/profile)."""
    leads, blocks = [], []
    for node, r in run["res"].items():
        for ep, l in r["out"][model]["leads"].items():
            leads.append(l); blocks.append(node * 10 + int(ep) // 2)
    leads, blocks = np.array(leads), np.array(blocks)
    rng = np.random.default_rng(seed)
    ub = np.unique(blocks)
    meds = []
    for _ in range(nboot):
        pick = rng.choice(ub, len(ub))
        meds.append(np.median(np.concatenate([leads[blocks == b] for b in pick])))
    return float(np.median(leads)), float(np.percentile(meds, 2.5)), float(np.percentile(meds, 97.5)), len(leads)
