# Fiche — Gateway FWI forecast (1 to 3 days)

**Runs on:** gateway, once per day and after each daily frame. **Spec:** §5.4 (gateway forecasts 1 to 3 days), §6 row 2. **Uses:** `../../box/fwi` for the physics.

## Role
Gives the expected FWI and danger class for the next 3 days, with an uncertainty range, so that the gateway can send the mode **Alert before the dangerous day** (spec §6, row 2).

## Input
Daily noon history from the boxes (`temp_c, rh_pct, wind_kmh, rain_mm`), the engine state (FFMC, DMC, DC), month, latitude. Optional: an external 1 to 3 day weather forecast (if the gateway can fetch one over 2G); when present it replaces the learned weather forecast.

## Output
For each day 1..3: FWI quantiles (10 %, 50 %, 90 %), `p_high` = P(class ≥ high), `class_median`.

## Design
Two methods, compared on the same data:
- **A. Hybrid ("weather, then physics")**: forecast the next days' noon weather as an ensemble (seasonal climatology + persistent anomalies, rain as a wet/dry Markov chain with gamma amounts), push every member through the **same engine** as the box (FFMC, DMC, DC, ISI, BUI, FWI), read quantiles. The physics is never learned, so it cannot be broken by the learning.
- **B. Direct gradient boosting**: predict the FWI at +k from lags and codes (quantile loss).
- Baselines: persistence (FWI today), "today's weather repeated".
- Challenger kept out of the run: Chronos-Bolt zero-shot (weights need Hugging Face, unreachable here); adapter interface documented.

## Metrics and pass criteria (set before running)
| Check | Criterion |
|---|---|
| Oracle consistency | with the true future weather, method A equals the engine's FWI (max abs diff ≤ 1e-9) |
| Engine vs published values (A data set) | report mean and max abs difference per component after a 20-day spin-up; no criterion (informative) |
| Synthetic multi-year, held-out years | MAE of the median FWI at +1, +2, +3 days ≤ persistence MAE, for A and for B |
| Interval calibration | empirical coverage of the 10–90 % interval between 0.70 and 0.90 |
| Real check (Algerian data set, leave-one-site-out) | MAE and coverage reported with block-bootstrap CI; no pass level (≈ 120 origins per site) |
| Runtime | 3-day forecast with 100 members < 100 ms on the host |

## Not done
- Training and evaluation on multi-year Tunisian weather (Open-Meteo / ERA5 download script provided).
- No numerical weather prediction input is tested; it would dominate the learned weather forecast beyond day 1.

## Known limits
- The synthetic generator and method A share assumptions (seasonality, AR(1)); the generator adds heat waves and wind events that A does not model, but the test remains easier than reality.
- A forecast from one box's own history cannot see fronts; rain timing is the main error.
