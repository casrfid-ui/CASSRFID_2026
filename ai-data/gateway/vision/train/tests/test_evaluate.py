import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluate import roc_ap, op_at_recall, bootstrap  # noqa: E402


def test_auc_matches_gaussian_theory():
    r = np.random.default_rng(0)
    y = np.r_[np.ones(6000, bool), np.zeros(6000, bool)]
    s = np.r_[r.normal(2, 1, 6000), r.normal(0, 1, 6000)]
    auc, ap = roc_ap(y, s)
    assert abs(auc - 0.9214) < 0.01                      # Phi(2 / sqrt 2)
    t, fpr = op_at_recall(y, s, 0.9)
    assert abs(t - 0.718) < 0.06 and abs(fpr - 0.236) < 0.02


def test_edge_cases():
    y = np.array([1, 1, 0, 0], bool)
    assert roc_ap(y, np.array([.9, .8, .2, .1]))[0] == 1.0
    assert roc_ap(y, np.array([.5, .5, .5, .5]))[0] == 0.5          # ties
    assert np.isnan(roc_ap(np.ones(4, bool), np.arange(4.))[0])
    assert np.isnan(op_at_recall(np.zeros(4, bool), np.arange(4.), 0.9)[0])


def test_group_bootstrap_is_wider_when_frames_are_duplicated():
    r = np.random.default_rng(1)
    base = r.normal(0, 1, 200)
    s_ind = np.r_[r.normal(2, 1, 400), r.normal(0, 1, 400)]
    y = np.r_[np.ones(400, bool), np.zeros(400, bool)]
    g_ind = np.arange(800)
    # same number of images, but 8 copies of 100 distinct frames per class: 200 groups
    s_dup = np.r_[np.repeat(r.normal(2, 1, 50), 8), np.repeat(r.normal(0, 1, 50), 8)]
    g_dup = np.r_[np.repeat(np.arange(50), 8), np.repeat(np.arange(50, 100), 8)]
    f = lambda s, i: op_at_recall(y[i], s[i], 0.9)[1]
    lo1, hi1 = bootstrap(g_ind, lambda i: f(s_ind, i), 300)
    lo2, hi2 = bootstrap(g_dup, lambda i: f(s_dup, i), 300)
    assert (hi2 - lo2) > 1.5 * (hi1 - lo1)
