import numpy as np
import pytest

from gw_common import (GRUModel, PlattCalibrator, auc, average_precision, block_bootstrap, brier, ece, far_at_recall,
                       graph, load_model, paired_block_bootstrap, save_model)


def test_auc_and_ap_match_sklearn():
    sk = pytest.importorskip("sklearn.metrics")
    rng = np.random.default_rng(0)
    y = rng.random(500) < 0.2
    s = rng.normal(size=500) + 1.2 * y
    s[:50] = np.round(s[:50])                           # ties
    assert abs(auc(y, s) - sk.roc_auc_score(y, s)) < 1e-12
    assert abs(average_precision(y, s) - sk.average_precision_score(y, s)) < 0.02   # step form vs interpolated ties


def test_perfect_and_random_scores():
    y = np.array([0, 0, 1, 1])
    assert auc(y, [0.1, 0.2, 0.8, 0.9]) == 1.0 and auc(y, [0.9, 0.8, 0.2, 0.1]) == 0.0
    assert np.isnan(auc([0, 0, 0], [1, 2, 3]))
    assert average_precision(y, [0.1, 0.2, 0.8, 0.9]) == 1.0
    assert brier([1, 0], [1.0, 0.0]) == 0.0


def test_far_at_recall():
    y = np.array([1] * 10 + [0] * 90)
    s = np.concatenate([np.linspace(0.5, 1, 10), np.linspace(0, 0.9, 90)])
    fpr, thr = far_at_recall(y, s, 0.9)
    assert (s[y == 1] >= thr).mean() >= 0.9 and 0 <= fpr <= 1


def test_platt_reduces_ece_on_overconfident_scores():
    rng = np.random.default_rng(1)
    true_p = rng.random(4000)
    y = rng.random(4000) < true_p
    s = np.clip(true_p ** 0.3, 0.001, 0.999)             # distorted scores
    cal = PlattCalibrator().fit(s[:2000], y[:2000])
    assert ece(cal.predict(s[2000:]), y[2000:]) < ece(s[2000:], y[2000:])


def test_block_bootstrap_is_wider_with_correlated_blocks():
    rng = np.random.default_rng(2)
    blocks = np.repeat(np.arange(40), 25)
    y = np.repeat(rng.random(40) < 0.3, 25)               # label constant inside a block
    s = rng.normal(size=40)[blocks] * 2.0 + 0.3 * rng.normal(size=1000) + 1.0 * y   # scores correlated inside a block
    _, lo_b, hi_b = block_bootstrap(auc, y, s, blocks, n=300)
    _, lo_i, hi_i = block_bootstrap(auc, y, s, np.arange(1000), n=300)
    assert (hi_b - lo_b) > (hi_i - lo_i)


def test_paired_difference_of_identical_scores_is_zero():
    rng = np.random.default_rng(3)
    y = rng.random(300) < 0.4
    s = rng.normal(size=300) + y
    d, lo, hi = paired_block_bootstrap(auc, y, s, s, np.arange(300), n=100)
    assert d == 0 and lo == 0 and hi == 0


def test_gru_numpy_equals_torch(tmp_path):
    torch = pytest.importorskip("torch")
    torch.manual_seed(0)
    gru = torch.nn.GRU(12, 16, batch_first=True)
    head = torch.nn.Linear(16, 3)
    x = torch.randn(200, 14, 12)
    with torch.no_grad():
        h, _ = gru(x)
        ref = head(h[:, -1]).numpy()
    m = GRUModel(gru.weight_ih_l0.detach().numpy(), gru.weight_hh_l0.detach().numpy(), gru.bias_ih_l0.detach().numpy(),
                 gru.bias_hh_l0.detach().numpy(), head.weight.detach().numpy(), head.bias.detach().numpy())
    out = m.forward(x.numpy(), standardised=True)
    assert np.abs(out - ref).max() <= 1e-5
    p = tmp_path / "m.npz"
    save_model(p, m, version="t")
    m2 = load_model(p)
    assert np.abs(m2.forward(x.numpy()) - out).max() == 0 and m2.meta["version"] == "t" and m.n_params() == 1.0 * m2.n_params()


def test_graph_layer_is_relabelling_invariant_and_handles_isolated_nodes():
    rng = np.random.default_rng(4)
    n, F, H = 6, 5, 8
    x = rng.normal(size=(n, F))
    src = np.array([0, 1, 1, 2, 3, 4]); dst = np.array([1, 0, 2, 1, 4, 3])    # node 5 isolated
    e = rng.normal(size=(len(src), 2))
    p = {"w_g": rng.normal(size=2), "b_g": 0.1, "w_self": rng.normal(size=(H, F)), "w_nb": rng.normal(size=(H, F)), "b": rng.normal(size=H)}
    params = {"layers": [p], "head_w": rng.normal(size=(1, H)), "head_b": np.zeros(1)}
    out = graph.forward(x, src, dst, e, params)
    perm = rng.permutation(n)
    inv = np.argsort(perm)
    out2 = graph.forward(x[perm], inv[src], inv[dst], e, params)
    assert np.abs(out2[inv] - out).max() < 1e-9
    iso = np.maximum(x[5] @ p["w_self"].T + p["b"], 0) @ params["head_w"].T
    assert abs(out[5] - iso[0]) < 1e-9
