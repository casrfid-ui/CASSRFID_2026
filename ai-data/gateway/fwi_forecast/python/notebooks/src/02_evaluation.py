# %% [markdown]
# # fwi_forecast 02 — Evaluation
# Criteria set in `FICHE.md` before running: median MAE at +1, +2, +3 ≤ persistence for both A and B; 10–90 % coverage in [0.70, 0.90]; 100-member forecast < 100 ms.
# Test seasons are never used for fitting the climate or the boosting models. Confidence intervals: block bootstrap over weeks.

# %%
import sys, pathlib, time
import numpy as np
ROOT = pathlib.Path.cwd().resolve().parents[1]
sys.path[:0] = [str(ROOT / "python/src"), str(ROOT.parent / "common/python/src"), str(ROOT.parents[1] / "box/fwi/python/src"), str(ROOT.parent / "risk_gru/python/src")]
from fwi_forecast import Climate, FwiForecaster, experiments as E

# %% [markdown]
# ## 1. Synthetic multi-year (evidence level S)
# 60 simulated seasons: 40 to fit, 20 to test (about 3 600 test origins).

# %%
ss = E.seasons(60, seed=11)
clim = Climate.fit(ss[:40])
tr = E.stack(ss[:40], clim)
te = E.stack(ss[40:], clim, with_A=True, members=100)
models = E.fit_B(tr["X"], tr["Y"])
B = E.predict_B(models, te["X"])
Y, bl = te["Y"], te["blocks"]
def show(name, pred):
    r = E.mae_row(pred, Y, bl)
    print(f"{name:14s}", "   ".join(f"+{h+1}d MAE {m:5.2f} [{lo:5.2f},{hi:5.2f}]" for h, (m, lo, hi) in enumerate(r)))
show("persistence", te["persistence"]); show("repeat today", te["repeat"]); show("A (hybrid)", te["A_q"][:, 1, :]); show("B (boosting)", B[:, 1, :])
print("10-90% coverage  A:", np.round(E.coverage(te["A_q"], Y), 3), " B:", np.round(E.coverage(B, Y), 3))

# %% [markdown]
# **Reading.** Both A and B beat persistence by a clear margin at every lead. A and B are statistically tied, which is the point of the design: A reaches B's accuracy while keeping the physics exact and needing no boosting library on the gateway.
# **Caveat.** The synthetic generator and method A share the same *kinds* of structure (seasonality, AR anomalies, a Markov rain chain); the test is easier than reality.

# %% [markdown]
# ## 2. Probability of a high-danger day
# `p_high` is the share of members with FWI ≥ 21.3 (class "high"). We check it with a Brier score against persistence-as-probability.

# %%
from gw_common import brier, average_precision, auc
yhigh = (Y >= 21.3).astype(float)
for h in range(3):
    print(f"+{h+1}d  Brier A {brier(yhigh[:, h], te['A_phigh'][:, h]):.3f} | AUROC A {auc(yhigh[:, h], te['A_phigh'][:, h]):.3f} | AUROC persistence {auc(yhigh[:, h], te['persistence'][:, h]):.3f} | base rate {yhigh[:, h].mean():.2f}")

# %% [markdown]
# ## 3. Real weather check — Algerian, leave-one-site-out (evidence level A)
# The climate is a *single mean per variable* from the other site (122 days cannot define a seasonal cycle). About 116 origins per site: report only, no pass level.
# Two variants, because section 1 of notebook 01 showed that **our engine does not reproduce the published codes of this data set**:
# - **(i) published codes**: state and truth are the published values (another implementation) while the ensemble goes through our engine → the method is judged against a different physics.
# - **(ii) own engine**: state and truth are computed by our engine from the real weather → this isolates the quality of the *weather forecast* on real weather.

# %%
alg = ROOT.parents[1] / "data/algerian/Algerian_forest_fires_dataset_UPDATE.csv"
for label, own in (("(i) published codes", False), ("(ii) own engine on real weather", True)):
    print("\n#####", label)
    ra = E.algerian_check(alg, own_engine=own)
    for site, v in ra.items():
        print(" ", site, "| origins:", len(v["Y"]))
        for name, p in (("persistence", v["persistence"]), ("repeat today", v["repeat"]), ("A (hybrid)", v["A_q"][:, 1, :])):
            r = E.mae_row(p, v["Y"], v["blocks"])
            print(f"    {name:13s}", "   ".join(f"+{h+1}d {m:5.2f} [{lo:5.2f},{hi:5.2f}]" for h, (m, lo, hi) in enumerate(r)))
        print("    coverage A:", np.round(E.coverage(v["A_q"], v["Y"]), 3))

# %% [markdown]
# ## 4. Run-time cost

# %%
s = ss[45]; i = 110
f = FwiForecaster(clim, 100, seed=1)
args = ((s["ffmc"][i], s["dmc"][i], s["dc"][i]), {k: s[k][i] for k in ("temp", "rh", "wind", "rain")}, int(s["doy"][i]))
f.forecast(*args)
t0 = time.perf_counter()
for _ in range(20): f.forecast(*args)
print("100 members x 3 days: %.1f ms per forecast (cloud CPU, not VIM4)" % ((time.perf_counter() - t0) / 20 * 1e3))
