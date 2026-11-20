# Research log — gateway block `risk_gru` (GRU ignition risk, day +1/+2/+3)

Fiche (criteria written before running): `ai-data/gateway/risk_gru/FICHE.md`. Code: `ai-data/gateway/risk_gru/python/`. Notebooks: `python/notebooks/`.
Every experiment is listed, including those that failed or did not meet the criteria.

## RES-RISK-1 — Synthetic world S1 (additive memory), 200 seasons, 5 GRU seeds (evidence level S)
- Setup: 120 train / 30 val / 50 test seasons, prevalence 0.06, horizons 1–3.
- Result (day +1, average precision): GRU, LR-window and GBM all ≈ 0.28–0.29; oracle ≈ 0.32. GRU/oracle AP = **0.895**.
- **Pre-registered criteria NOT met**: (a) GRU AP ≥ 0.90 × oracle → 0.895; (b) GRU − LR-current ≥ +0.02 AP → +0.015.
- Interpretation: with additive memory, the engineered FWI codes and a linear model already capture what is learnable; recurrence adds nothing measurable. This is the expected null result, not a bug (oracle gap is mostly irreducible Bernoulli noise).
- A first run with only 40 seasons was too noisy to conclude and also missed the criteria; it is not used.

## RES-RISK-2 — Synthetic world S2 (non-additive memory: heat-wave run × wind²)
- 200 seasons: GRU AP 0.391, GBM 0.401, LR-current 0.289. GRU and GBM are statistically tied and both clearly above LR-current.
- Notebook run (60 seasons, 2 seeds): GRU 0.356 [0.255, 0.458], GBM 0.296, LR-cur 0.278, oracle 0.581 — same ordering, wide intervals.
- Interpretation: when memory interacts non-linearly, a sequence model or a tree model beats a linear one. The GRU is **not** better than gradient boosting. The honest argument for the GRU is therefore not accuracy but the single-model, three-horizon output and the cheap numpy runtime.

## RES-RISK-3 — Real data, Algerian Forest Fires (evidence level A), leave-one-site-out
- ≈ 85–89 test windows per site (46 / 63 positives at h=1). Block bootstrap over consecutive weeks.
- Day +1, AUROC / AP (200-run setting, 5 seeds):

| test site | persistence | FWI threshold | LR current | GBM | GRU |
|---|---|---|---|---|---|
| Bejaia | 0.775 / 0.741 | **0.833 / 0.791** | 0.767 / 0.779 | 0.586 / 0.588 | 0.728 / 0.717 |
| Sidi Bel Abbes | 0.671 / 0.879 | **0.736 / 0.866** | 0.640 / 0.777 | 0.646 / 0.813 | 0.662 / 0.826 |

- The plain FWI threshold is the best or tied-best scorer at every horizon; confidence intervals (≈ ±0.1) overlap, so no learned model is shown worse or better with confidence, but none is shown better.
- Notebook run (2 seeds, 40 epochs) gives the same picture (GRU 0.690 AUROC on Bejaia).
- Caveats: "fire" is a daily class, ≈ half the days are positive (field prevalence is a few percent); the two sites are in the same summer, so leave-one-site-out is only a weak test of generalisation.

## RES-RISK-4 — Data issues found and fixed
- The CSV has a second header row mid-file → parser requires a numeric first field.
- One row (Bejaia 14/07/2012) has an **empty class**. It was first read as "not fire" (file = 137 fire + 106 not fire + 1 blank; UCI reports 138/106). Fixed: kept as NaN, windows touching it are dropped. We did not impute (UCI's count suggests "fire" but we cannot verify).
- The first Algerian run used one bootstrap block per site, giving zero-width intervals. Fixed: blocks = consecutive weeks.
- First synthetic hazard gave prevalence 0.0004 (intercept never solved). Fixed: intercept by bisection to the target prevalence. First weather generator was too extreme (FWI p99 124) and was retuned (summer FWI q10/50/90/99 ≈ 10/26/46/89).
- A unit test of the bootstrap assumed i.i.d. scores; wrong premise (block CI is wider only with correlated scores). Test rewritten.

## RES-RISK-5 — Cost
- Demo model: 1 491 parameters, 16 KB `.npz`; numpy update ≈ 0.2 ms per box-day on the cloud CPU. **Not measured on the VIM4.**
- Calibration (Platt on validation seasons), synthetic S1: ECE 0.016 on test.

## Status and what may be claimed
- Claimable: the block exists, is leak-free by construction, runs on numpy in sub-millisecond, and is evaluated with block-bootstrap intervals and an oracle.
- **Not claimable**: that it predicts real Tunisian fires better than the FWI threshold. The `risk_gru_demo_synthetic.npz` model has never seen a real fire.
- To get level P evidence: run `scripts/fetch_open_meteo.py` (daily weather for the two box sites) and a FIRMS hotspot download on a PC with internet, then `datasets.from_weather_and_hotspots` (not executed here — no network access to these services).
