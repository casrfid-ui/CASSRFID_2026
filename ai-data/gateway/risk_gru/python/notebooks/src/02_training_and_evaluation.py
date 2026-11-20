# %% [markdown]
# # risk_gru 02 — Training, evaluation, honesty
# Criteria were written in `FICHE.md` **before** running. This notebook runs a reduced version (60 seasons, 2 seeds) so it executes in minutes;
# the full figures (200 seasons, 5 seeds) are in `docs/research/gateway-risk-gru.md`.
#
# **Model.** A 1-layer GRU (hidden 16, ≈1.5 k parameters) reading 14 daily vectors of 12 features, then a linear head giving 3 logits (day +1, +2, +3).
# Loss: binary cross-entropy with half-strength positive weighting (fires are rare). Early stopping on validation average precision.
# **Why a GRU and not an LSTM.** Fewer parameters, same job for 14 steps, and the numpy re-implementation on the gateway is shorter (3 gates instead of 4).

# %%
import sys, pathlib, time
import numpy as np
import matplotlib.pyplot as plt
ROOT = pathlib.Path.cwd().resolve().parents[1]
sys.path[:0] = [str(ROOT / "python/src"), str(ROOT.parent / "common/python/src"), str(ROOT.parents[1] / "box/fwi/python/src")]
from risk_gru import experiments as E, predictor
from gw_common import reliability, ece

# %% [markdown]
# ## 1. S1 — memory is additive
# Baselines: *persistence* (is there a fire today?), *fwi_threshold* (the operational rule), logistic regression on today's values (*lr_cur*) and on the whole window (*lr_win*),
# gradient boosting (*gbm*), and the *oracle* (the true probability, unreachable in practice).

# %%
r1 = E.run_synthetic(60, seed=0, gru_seeds=2, epochs=40)
Xte, Yte, mte = r1["data"][2]
def show(rows, h=1):
    print(f"{'model':14s} {'AUROC':>6s} {'AP':>6s}  AP 95% block-bootstrap CI")
    for n, hh, a, alo, ahi, p, plo, phi, b in rows:
        if hh == h: print(f"{n:14s} {a:6.3f} {p:6.3f}  [{plo:.3f}, {phi:.3f}]")
show(E.table(r1["scores"], Yte, mte["block"]))

# %% [markdown]
# **Reading.** If the GRU is not clearly above `lr_cur` here, the recurrence adds nothing when the memory is additive: the engineered FWI codes already summarise the past.

# %% [markdown]
# ## 2. S2 — non-additive memory
# Same weather; the hazard now contains (length of the current heat wave) × (wind)². This is the case a recurrent network is *supposed* to help.

# %%
r2 = E.run_synthetic(60, seed=0, gru_seeds=2, epochs=40, variant="interaction")
show(E.table(r2["scores"], r2["data"][2][1], r2["data"][2][2]["block"]))

# %% [markdown]
# ## 3. Real data — Algerian, leave-one-site-out (evidence level A)
# Train on one site, test on the other. About 85–89 windows per test site: **wide intervals, no strong claim possible**.

# %%
alg = ROOT.parents[1] / "data/algerian/Algerian_forest_fires_dataset_UPDATE.csv"
ra = E.run_algerian(alg, gru_seeds=2, epochs=40)
for site, v in ra.items():
    print("\n== test site:", site, "| windows:", len(v["Y"]), "| positives h=1:", int(v["Y"][:, 0].sum()))
    show(E.table(v["scores"], v["Y"], v["meta"]["block"]))

# %% [markdown]
# ## 4. Calibration (synthetic S1)
# A probability that is not calibrated cannot be thresholded sensibly. We fit a Platt scaling on the validation seasons and look at the reliability curve on the test seasons.

# %%
from risk_gru.train import calibrated
p = calibrated(r1["model"], r1["calib"], Xte)[:, 0]
rel = reliability(Yte[:, 0], p, bins=8)
cx, cy = [r[0] for r in rel], [r[1] for r in rel]
print("ECE (day +1):", round(ece(p, Yte[:, 0]), 4), "| bin counts:", [r[2] for r in rel])
plt.figure(figsize=(4, 4)); plt.plot([0, max(cx)], [0, max(cx)], "k--"); plt.plot(cx, cy, "o-"); plt.xlabel("predicted"); plt.ylabel("observed"); plt.title("reliability, day +1"); plt.show()

# %% [markdown]
# ## 5. Cost on the gateway
# The runtime class uses numpy only. One update = one day for one box.

# %%
MODEL = ROOT / "models/risk_gru_demo_synthetic.npz"
pr = predictor.RiskPredictor(MODEL)
day = dict(temp=34, rh=28, wind=18, rain=0.0, ffmc=92, dmc=90, dc=400, isi=12, bui=100, fwi=30, month=7)
for _ in range(14): pr.update(day)
t0 = time.perf_counter()
for _ in range(2000): out = pr.update(day)
print(out, "\nmean time per update: %.3f ms (this cloud CPU; not measured on the VIM4)" % ((time.perf_counter() - t0) / 2000 * 1e3))
print("model file bytes:", MODEL.stat().st_size)

# %% [markdown]
# ## 6. Conclusions to carry forward (see research log for full numbers)
# - The pipeline is correct (oracle gap measured, parity with numpy tested, no leakage by construction).
# - On additive synthetic memory the GRU matches simple models; the oracle gap is mostly irreducible noise.
# - On real Algerian data, the plain FWI threshold is the best single scorer; learned models do not beat it with 85 test windows.
# - Therefore: **the GRU is a research/demonstration block, not a proven improvement.** The only claim we may make is that it runs on the gateway in well under a millisecond and that we know how to evaluate it honestly.
