# %% [markdown]
# # gas_trend 02 — Does a trend model warn earlier than the chain?
# Pass criteria were fixed in `FICHE.md` before running: numpy GRU = PyTorch (≤ 1e-5, unit test), no node shared (unit test), **false flags per hour on clean air ≤ the chain's**, lead time reported with a bootstrap CI (no pass level; if the CI includes 0 → "no earlier than the chain"), < 1 ms per update.
# Models: `chain_depth` (threshold on the chain's depth: the chain itself with a lower threshold), `slope_rule` (extrapolate depth 8 scans ahead), `logistic` (window features), `gru` (hidden 12, 769 parameters).

# %%
import sys, pathlib, time
import numpy as np
ROOT = pathlib.Path.cwd().resolve().parents[1]
sys.path[:0] = [str(ROOT / "python/src"), str(ROOT.parent / "common/python/src"), str(ROOT.parents[1] / "box/gas_chain/python/src")]
from gas_chain import data_mendeley as D
from gas_trend import experiments as E
data = D.load_all()

# %%
runs = {}
for factor in (1.0, 0.5, 0.25):
    runs[factor] = E.run_factor(factor, data, gru_seeds=3, epochs=40)
    print("factor", factor, "done")

# %% [markdown]
# ## Lead time and false alarms (median over episodes; missed = lead 0; CI = bootstrap over recordings)

# %%
print(f"{'factor':>6s} {'model':12s} {'median lead s':>13s} {'95% CI':>16s} {'episodes':>8s} {'missed':>7s} {'FA/h nodes 1..5':>30s}   chain FA/h")
for factor, run in runs.items():
    for m in E.MODELS:
        med, lo, hi, n = E.lead_summary(run, m)
        missed = sum(r["out"][m]["missed"] for r in run["res"].values())
        fa = [round(r["out"][m]["fa_per_hour"], 1) for r in run["res"].values()]
        cfa = [round(float(r["out"][m]["chain_fa_per_hour"]), 1) for r in run["res"].values()]
        print(f"{factor:6.2f} {m:12s} {med:13.0f} [{lo:6.0f},{hi:6.0f}] {n:8d} {missed:7d} {str(fa):>30s}   {cfa if m == 'gru' else ''}")

# %% [markdown]
# ## Window-level ranking (AUROC / AP of 'onset within 8 scans', per test node, factor 1.0)

# %%
for m in E.MODELS:
    print(f"{m:12s} AUROC", [round(r["out"][m]["auc"], 2) for r in runs[1.0]["res"].values()], " AP", [round(r["out"][m]["ap"], 2) for r in runs[1.0]["res"].values()])
print("positive rate:", round(float(runs[1.0]["meta"]["y"].mean()), 3))

# %% [markdown]
# ## How to read the result
# 1. **Criterion 'false flags ≤ chain's'**: look at the FA/h columns against the chain's. A model that exceeds the chain's rate on a test node *fails* the criterion on that node, whatever its lead time — a lead time bought with false alarms is worthless.
# 2. **Lead time**: if the CI includes 0, the conclusion is "no earlier than the chain".
# 3. Small sample: 38 episodes from 20 recordings of 2 burns; intervals are wide and the dilution factors are not independent experiments.
