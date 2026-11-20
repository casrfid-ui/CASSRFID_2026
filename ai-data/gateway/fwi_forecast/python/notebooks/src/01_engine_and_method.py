# %% [markdown]
# # fwi_forecast 01 — The FWI engine and the two forecasting methods
# **Goal.** Tell the gateway, one to three days ahead, how dangerous the weather will be — as a **range**, not a single number — so that it can alert *before* the dangerous day.
#
# **Design in one sentence.** Forecast the *weather* (not the index), then push it through the *same FWI engine the box runs*, so the physics is never learned and cannot be damaged by learning.
#
# **Contents.** (1) the engine and a check against published values, (2) how the weather ensemble is built, (3) the comparison method (gradient boosting), (4) an oracle test.

# %%
import sys, pathlib
import numpy as np
import matplotlib.pyplot as plt
ROOT = pathlib.Path.cwd().resolve().parents[1]
sys.path[:0] = [str(ROOT / "python/src"), str(ROOT.parent / "common/python/src"), str(ROOT.parents[1] / "box/fwi/python/src"), str(ROOT.parent / "risk_gru/python/src")]
from fwi_forecast import Climate, FwiForecaster, experiments as E
from fwi_forecast.ensemble import WeatherEnsemble

# %% [markdown]
# ## 1. The engine (reminder) and a check on real published values
# Daily chain: FFMC (fine fuel, hours), DMC (duff, weeks), DC (deep layer, months) → ISI (spread) and BUI (fuel available) → FWI.
# Class limits used (EFFIS): 5.2 / 11.2 / 21.3 / 38 / 50.
#
# The Algerian data set publishes the codes for 2 sites. We run **our** engine from the standard start values on the same weather and compare after 20 days of spin-up.
# This is informative only (no pass level): the published values start from unknown state and may use a different latitude constant for DMC/DC day length.

# %%
from risk_gru import datasets
alg = ROOT.parents[1] / "data/algerian/Algerian_forest_fires_dataset_UPDATE.csv"
tabs = datasets.algerian(alg)
res = E.engine_vs_published(tabs)
print(f"{'site':14s} {'code':5s} {'mean |diff|':>11s} {'max |diff|':>11s}")
for (site, k), (m, mx) in res.items(): print(f"{site:14s} {k:5s} {m:11.2f} {mx:11.2f}")

# %% [markdown]
# **How to read it.** Small differences on FFMC/ISI (they forget quickly) and larger on DMC/DC/BUI (they remember the start state and depend on the day-length table) is the expected pattern.
# The gap is documented in the research log; we do not "fix" the engine to match, because the box and the gateway must use the same code.

# %% [markdown]
# ## 2. The weather ensemble
# Learned from a training record, with nothing assumed about the data generator:
# 1. a smooth **seasonal mean** of temperature, humidity and wind per day of the year;
# 2. the **anomaly** (today minus mean) fades with the lead time: `a(t+k) ≈ φ_k · a(t) + noise(σ_k)`, with φ_k, σ_k fitted;
# 3. **rain** is a wet/dry chain (P(wet | dry) varies with the date, P(wet | wet) constant) with **gamma** amounts;
# 4. a wet day shifts T and RH by the average amount seen on wet days.
# 100 members are drawn; each goes through the engine; the quantiles of their FWI are the forecast.

# %%
ss = E.seasons(60, seed=11)
clim = Climate.fit(ss[:40])
print("phi(temp) by lead:", np.round(clim.phi["temp"], 2), "| sigma(temp):", np.round(clim.sigma["temp"], 2))
print("wet-day shift:", {k: round(v, 2) for k, v in clim.wet_shift.items()}, "| P(wet|wet):", round(clim.markov["p_ww"], 2), "| rain gamma:", {k: round(v, 2) for k, v in clim.gamma.items()})

# %%
s = ss[45]; i = 110
fc = FwiForecaster(clim, 100, seed=1).forecast((s["ffmc"][i], s["dmc"][i], s["dc"][i]), {k: s[k][i] for k in ("temp", "rh", "wind", "rain")}, int(s["doy"][i]))
for d in fc: print(d)
print("truth FWI +1..+3:", np.round(s["fwi"][i + 1:i + 4], 1))

# %% [markdown]
# ## 3. Oracle test (a correctness check, not a performance claim)
# Feed the *true* future weather to the engine: the result must equal the FWI of the data to machine precision. If not, the forecaster has a bug of its own.

# %%
print("max |oracle - truth| over 100 origins:", max(np.max(np.abs(E.oracle(s, j) - s["fwi"][j + 1:j + 4])) for j in range(40, 140)))

# %% [markdown]
# ## 4. Comparison method B — direct quantile gradient boosting
# 9 models (3 days × quantiles 10/50/90) on 15 features: FWI today and 2 lags, the three codes, today's weather, anomalies, month.
# B learns the whole mapping at once and has **no physics**. On the gateway we deploy only method A (numpy + engine); B needs scikit-learn and is a yardstick.

# %%
tr = E.stack(ss[:40], clim)
models = E.fit_B(tr["X"], tr["Y"])
print("trained", len(models), "quantile models on", len(tr["X"]), "origins")
