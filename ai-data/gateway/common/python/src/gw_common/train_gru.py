"""Generic GRU training with PyTorch (PC only; imported lazily so that the gateway never needs torch).
Same recipe as risk_gru.train.fit_gru: Adam, half-strength positive weight, early stopping on validation mean average precision."""
import numpy as np

from .gru import GRUModel
from .metrics import average_precision


def fit_gru(Xtr, Ytr, Xva, Yva, seed=0, hidden=16, meta=None, epochs=80, patience=10, lr=3e-3, batch=128, wd=1e-4, verbose=False):
    """Returns (GRUModel in numpy, history dict). Selection on the validation mean average precision over the horizons."""
    import torch
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
                     meta=dict(meta or {}))
    hist["best_val_ap"] = best; hist["epochs_run"] = len(hist["loss"])
    return model, hist


