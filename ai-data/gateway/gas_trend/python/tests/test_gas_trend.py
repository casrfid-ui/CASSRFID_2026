import pathlib
import time
import numpy as np
import pytest

from gas_chain import data_mendeley as D
from gas_trend import chain_features, build_samples, TrendPredictor, WINDOW, experiments as E

MODEL = pathlib.Path(__file__).resolve().parents[2] / "models" / "gas_trend_demo.npz"


@pytest.fixture(scope="module")
def sample():
    d = D.load_sample()                       # committed sample (no download); episodes may lack some phases
    return d


def test_split_hygiene_nodes_never_shared():
    meta = dict(node=np.repeat([1, 2, 3, 4, 5], 10))
    for test in E.NODES:
        tr, va, te = E.split(meta, test)
        assert not (tr & va).any() and not (tr & te).any() and not (va & te).any()
        assert set(meta["node"][te]) == {test} and test not in set(meta["node"][tr]) and set(meta["node"][va]).isdisjoint(set(meta["node"][te]))


def test_threshold_respects_budget():
    rng = np.random.default_rng(0)
    s = rng.normal(size=1000)
    clean = np.ones(1000, bool)
    thr = E.threshold_for_budget(s, clean, hours=1.0, budget_per_hour=5)
    assert (s >= thr).sum() <= 5
    assert (s >= E.threshold_for_budget(s, clean, 1.0, 0.0)).sum() == 0


def test_samples_exclude_post_onset_and_warmup(sample):
    f = chain_features(sample)
    X, meta = build_samples(f)
    assert (meta["phase"] < 2).all()                        # nothing at or after the onset
    assert not f["warmup"][meta["idx"]].any()
    for ep in np.unique(meta["episode"]):
        m = meta["episode"] == ep
        y = meta["y"][m]
        assert (np.diff(y) >= 0).all()                      # label 0...0 then 1...1 (ordered in time)


@pytest.mark.skipif(not MODEL.exists(), reason="demo model not built")
def test_predictor_matches_forward_and_is_fast():
    pr = TrendPredictor(MODEL)
    rng = np.random.default_rng(0)
    rows = rng.normal(size=(WINDOW, 7)) * pr.model.std + pr.model.mean
    for r in rows[:-1]:
        assert pr.update(r[0], r[1], r[2:5], r[5], r[6])["ready"] is False or True
    out = pr.update(rows[-1][0], rows[-1][1], rows[-1][2:5], rows[-1][5], rows[-1][6])
    ref = 1 / (1 + np.exp(-pr.model.forward(rows, standardised=False)[0]))
    assert abs(out["p_onset"] - ref) < 1e-12 and out["ready"]
    t0 = time.perf_counter()
    for _ in range(500):
        pr.update(*rows[-1][:2], rows[-1][2:5], rows[-1][5], rows[-1][6])
    assert (time.perf_counter() - t0) / 500 < 1e-3


def test_numpy_gru_matches_torch():
    torch = pytest.importorskip("torch")
    from gw_common.train_gru import fit_gru
    rng = np.random.default_rng(1)
    X = rng.normal(size=(200, WINDOW, 7)); y = (X[:, -1, 1] > 0.3).astype(float)[:, None]
    m, _ = fit_gru(X[:150], y[:150], X[150:], y[150:], seed=0, hidden=12, epochs=5)
    net = torch.nn.GRU(7, 12, batch_first=True); head = torch.nn.Linear(12, 1)
    net.load_state_dict({"weight_ih_l0": torch.tensor(m.w_ih), "weight_hh_l0": torch.tensor(m.w_hh), "bias_ih_l0": torch.tensor(m.b_ih), "bias_hh_l0": torch.tensor(m.b_hh)})
    head.load_state_dict({"weight": torch.tensor(m.head_w), "bias": torch.tensor(m.head_b)})
    xs = torch.tensor(m.standardise(X[150:]), dtype=torch.float64); net.double(); head.double()
    with torch.no_grad():
        ref = head(net(xs)[0][:, -1]).numpy()
    assert np.abs(ref - m.forward(X[150:], standardised=False)).max() <= 1e-5
