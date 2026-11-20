"""Trains the DEMO model (nodes 1-4 train, node 5 validation/threshold) on the public BME688 recordings and writes models/gas_trend_demo.npz.
Trained on the same 5 nodes the evaluation uses, so it carries NO held-out evidence. It exists to exercise the gateway code path."""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(HERE.parent / "src"), str(ROOT.parent / "common/python/src"), str(ROOT.parents[1] / "box/gas_chain/python/src")]
import numpy as np  # noqa: E402
from gas_chain import data_mendeley as D  # noqa: E402
from gas_trend import chain_features, build_samples, experiments as E  # noqa: E402
from gw_common import save_model  # noqa: E402
from gw_common.train_gru import fit_gru  # noqa: E402

if __name__ == "__main__":
    f = chain_features(D.load_all())
    X, meta = build_samples(f)
    tr, va = meta["node"] != 5, meta["node"] == 5
    best = None
    for s in range(3):
        m, h = fit_gru(X[tr], meta["y"][tr][:, None], X[va], meta["y"][va][:, None], seed=s, hidden=12, epochs=40, patience=8,
                       meta=dict(horizon=8))
        if best is None or h["best_val_ap"] > best[1]["best_val_ap"]:
            best = (m, h)
    m = best[0]
    sc = m.forward(X, standardised=False)[:, 0]
    clean = va & (meta["phase"] == 0)
    thr = E.threshold_for_budget(sc, clean, E.clean_hours(meta, va), 0.0)
    m.meta.update(threshold=float(thr), provenance="DEMO: GRU trained on public BME688 nodes 1-4, threshold on node 5 clean air (0 false flags). No held-out evidence.")
    out = ROOT / "models" / "gas_trend_demo.npz"
    save_model(out, m, **m.meta)
    print(out, out.stat().st_size, "bytes", m.n_params(), "parameters, threshold", round(thr, 3))
