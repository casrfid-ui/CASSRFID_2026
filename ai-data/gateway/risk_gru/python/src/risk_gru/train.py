"""Training on a PC (PyTorch). Produces numpy weights for the gateway. Hyper-parameters are fixed in the code, not tuned on test data."""
import json

import numpy as np

from gw_common import GRUModel, PlattCalibrator, average_precision, save_model
from .features import FEATURES, HORIZONS

HIDDEN = 16


def _torch():
    import torch
    return torch


def fit_gru(Xtr, Ytr, Xva, Yva, seed=0, hidden=HIDDEN, epochs=80, patience=10, lr=3e-3, batch=128, wd=1e-4, verbose=False):
    """Returns (GRUModel in numpy, history dict). Selection on the validation mean average precision over the horizons."""
    torch = _torch()
    torch.manual_seed(seed); np.random.seed(seed)
    mean = Xtr.reshape(-1, Xtr.shape[-1]).mean(0)
    std = Xtr.reshape(-1, Xtr.shape[-1]).std(0) + 1e-6

    class Net(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.gru = torch.nn.GRU(Xtr.shape[-1], hidden, batch_first=True)
            self.head = torch.nn.Linear(hidden, Ytr.shape[1])

        def forward(self, x):
            h, _ = self.gru(x)
            return self.head(h[:, -1])

    net = Net()
    opt = torch.optim.Adam(net.parameters(), lr=lr, weight_decay=wd)
    xt = torch.tensor((Xtr - mean) / std, dtype=torch.float32); yt = torch.tensor(Ytr, dtype=torch.float32)
    xv = torch.tensor((Xva - mean) / std, dtype=torch.float32)
    pos = np.clip(Ytr.mean(0), 1e-3, 1 - 1e-3)
    pw = torch.tensor(np.sqrt((1 - pos) / pos), dtype=torch.float32)          # half-strength class weight
    lossf = torch.nn.BCEWithLogitsLoss(pos_weight=pw)
    best, best_state, bad, hist = -1.0, None, 0, {"loss": [], "val_ap": []}
    n = len(xt)
    for ep in range(epochs):
        net.train()
        perm = torch.randperm(n)
        tot = 0.0
        for i in range(0, n, batch):
            idx = perm[i:i + batch]
            opt.zero_grad()
            loss = lossf(net(xt[idx]), yt[idx])
            loss.backward(); opt.step()
            tot += loss.item() * len(idx)
        net.eval()
        with torch.no_grad():
            pv = torch.sigmoid(net(xv)).numpy()
        ap = float(np.nanmean([average_precision(Yva[:, h], pv[:, h]) for h in range(Yva.shape[1])]))
        hist["loss"].append(tot / n); hist["val_ap"].append(ap)
        if verbose:
            print(ep, round(tot / n, 4), round(ap, 4))
        if ap > best + 1e-5:
            best, bad = ap, 0
            best_state = {k: v.detach().clone() for k, v in net.state_dict().items()}
        else:
            bad += 1
            if bad >= patience:
                break
    net.load_state_dict(best_state)
    sd = {k: v.numpy() for k, v in net.state_dict().items()}
    model = GRUModel(sd["gru.weight_ih_l0"], sd["gru.weight_hh_l0"], sd["gru.bias_ih_l0"], sd["gru.bias_hh_l0"],
                     sd["head.weight"], sd["head.bias"], mean, std,
                     meta={"features": list(FEATURES), "horizons": list(HORIZONS)})
    hist["best_val_ap"] = best; hist["epochs_run"] = len(hist["loss"])
    return model, hist


def _apply(c, s):
    s = np.clip(np.asarray(s, float), 1e-4, 1 - 1e-4)
    return 1.0 / (1.0 + np.exp(-(c["a"] * np.log(s / (1 - s)) + c["b"])))


def calibrate(model, Xva, Yva):
    """One Platt calibrator per horizon, fitted on the validation windows. Returns a list of {"a","b"}."""
    p = model.predict_proba(Xva, standardised=False)
    out = []
    for h in range(Yva.shape[1]):
        c = PlattCalibrator().fit(p[:, h], Yva[:, h])
        out.append({"a": c.a, "b": c.b})
    return out


def calibrated(model, calib, X):
    p = model.predict_proba(X, standardised=False)
    return np.stack([_apply(calib[h], p[:, h]) for h in range(p.shape[1])], 1)


def thresholds(model, calib, Xva, Yva, recall_moderate=0.95, recall_high=0.80):
    """Level thresholds on the maximum calibrated risk over the horizons: moderate reaches 95 %, high 80 % of the validation fire days (any horizon)."""
    pm = calibrated(model, calib, Xva).max(1)
    pos = np.sort(pm[Yva.max(1) > 0])[::-1]
    f = lambda r: float(pos[int(np.ceil(r * len(pos))) - 1]) if len(pos) else 1.0
    return {"moderate": f(recall_moderate), "high": f(recall_high)}


def save_deployable(path, model, calib, thr, provenance):
    save_model(path, model, calibration=calib, thresholds=thr, provenance=provenance)
    return path
