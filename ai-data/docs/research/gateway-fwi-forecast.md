# Research log — gateway block `fwi_forecast` (FWI 1–3 days ahead)

Fiche (criteria first): `ai-data/gateway/fwi_forecast/FICHE.md`. Code: `.../fwi_forecast/python/`. Notebooks: `python/notebooks/`.

## RES-FWIF-1 — Oracle consistency (criterion: max abs diff ≤ 1e-9) — PASSED
Engine fed with the true future weather reproduces the data's FWI exactly (difference 0.0 on 100 origins; also a unit test).

## RES-FWIF-2 — Synthetic held-out seasons (evidence level S): 40 seasons to fit, 20 to test, 3 620 origins
Median-forecast MAE (FWI units), 95 % block-bootstrap CI:

| method | +1 d | +2 d | +3 d |
|---|---|---|---|
| persistence | 6.84 [6.47, 7.22] | 8.93 [8.41, 9.50] | 9.97 [9.41, 10.57] |
| today's weather repeated | 6.89 | 9.13 | 10.32 |
| **A hybrid** (weather ensemble → engine) | 5.97 [5.66, 6.28] | 7.35 [7.00, 7.75] | 7.82 [7.41, 8.24] |
| **B** direct quantile boosting | 5.91 [5.58, 6.22] | 7.21 [6.83, 7.60] | 7.74 [7.36, 8.14] |

- Criterion "A and B ≤ persistence at every lead" — **PASSED** (CIs do not overlap persistence at +2, +3).
- Criterion "10–90 % coverage in [0.70, 0.90]" — **PASSED**: A 0.79 / 0.77 / 0.76, B 0.78 / 0.78 / 0.78.
- A and B are tied. The learned climate recovered the generator's structure (lead-1 AR coefficient 0.71, wet-day shift −3.1 °C / +9.5 % RH), which is expected since both share the same kinds of structure: **this is the easy case**.
- P(high) (share of members ≥ 21.3): AUROC 0.89 / 0.84 / 0.81 at +1/+2/+3 d vs persistence 0.87 / 0.80 / 0.76.

## RES-FWIF-3 — Engine vs published codes of the Algerian data set — **UNRESOLVED DISCREPANCY (informative criterion, large gap)**
Our box engine (start 85 / 6 / 15 at the first day) on the data set's weather, after 20 days:
- mean |diff|: FFMC 7.2 / 4.8, DMC 83 / 71, DC 473 / 536, ISI 2.0 / 2.1, BUI 105 / 107, FWI 15.0 / 19.2 (Bejaia / Sidi Bel Abbes).
- Correlation of our codes with the published ones: FFMC 0.84 / 0.81, ISI 0.73 / 0.85, FWI 0.69 / 0.78, DC only 0.40 / 0.36.
- Published maxima are far lower than ours (DMC 54–66 vs 179–224; DC 177–220 vs 824–904), i.e. the published DMC/DC look like they were computed from different starting values, or a different implementation, or carry errors.
- We did **not** conclude that our engine is wrong (it follows the reference equations; its own tests are in `ai-data/box/fwi`), and we did **not** change it. Possible causes to check later: pre-season start state, rain handling, day-length constants. Until then, **the Algerian data set cannot be used to validate the engine**, and any experiment mixing its published codes with our engine is judged against different physics.

## RES-FWIF-4 — Real-weather check, Algerian, leave-one-site-out (evidence level A, 116 origins/site, no pass level)
(i) State and truth = published codes (mixed physics): A is at best equal to persistence (Bejaia +1 d 3.05 vs 2.85) and better at Sidi Bel Abbes (+3 d 6.18 vs 7.99), but coverage is 0.37–0.54 — the mismatch of physics makes intervals wrong. Not a valid test of the method.
(ii) State and truth from our engine on the real weather (isolates the weather forecast):

| site | +1 d MAE persistence / A | +3 d MAE persistence / A | coverage 10–90 % (+1, +2, +3) |
|---|---|---|---|
| Bejaia | 3.49 / 3.34 | 6.07 / 6.13 | 0.91, 0.88, 0.86 |
| Sidi Bel Abbes | 6.51 / 6.91 | 11.31 / 11.21 | 0.62, 0.47, 0.41 |

- On real weather A **ties persistence** (all CIs overlap); it does not beat it. Coverage is good at Bejaia and poor at Sidi Bel Abbes, where the other site's constant climate is not representative.
- 122 days cannot define a seasonal cycle; a proper test needs several real seasons (script for ERA5 in `risk_gru/python/scripts/fetch_open_meteo.py`, not run here).

## RES-FWIF-5 — Cost
100 members × 3 days through the engine: 2.8 ms per forecast on the cloud CPU (criterion < 100 ms — PASSED; **not measured on the VIM4**).

## Not done
- Chronos-Bolt zero-shot (weights unreachable here). External weather forecast input exists (`external=` argument, unit-tested) but no real forecast feed was tested.
- Training on real multi-year Tunisian weather.

## What may be claimed
The block is correct (oracle test), cheap, gives calibrated-looking ranges on synthetic data and a **probability of a high-danger day**. We may **not** claim it beats persistence on real weather.
