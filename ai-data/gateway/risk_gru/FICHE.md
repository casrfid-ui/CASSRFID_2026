# Fiche — Gateway ignition-risk model (GRU)

**Runs on:** gateway (Raspberry Pi 4 / Khadas VIM4, CPU, numpy only). **Spec:** §5.4 and §6 (row 2, forecast side), fast and slow path. **Inputs come from:** `../../box/fwi`.
**Decision of the team (12 Nov):** prediction models only (no CNN); the YOLO detector stays the only vision model.

## Role
Reads the last 14 days of daily weather and FWI codes and gives, for each of the next 3 days, the probability that a fire occurs near the box. It does **not** replace the FWI: it learns what the FWI cannot, namely how dryness accumulates and how the last days combine.
The box never depends on it: the FWI class and the gas chain keep deciding alone (spec principle 1).

## Input (one row per day, local noon)
`temp_c, rh_pct, wind_kmh, rain_mm, ffmc, dmc, dc, isi, bui, fwi` (from the box engine) + `sin/cos(month)`. 12 features, window of 14 days.

## Output
`p_day1, p_day2, p_day3` (calibrated), `level` (`low | moderate | high`, thresholds chosen on validation), `provisional` (window not full), `model` (version, training data).

## Design
- One GRU layer (hidden 16) + one linear head with 3 sigmoid outputs: about 1.7 k parameters, 7 kB.
- Trained on a PC with PyTorch; the gateway runs a **numpy** re-implementation (no torch on the SBC); parity is tested.
- Inputs standardised with statistics saved in the model file; missing day = previous day repeated and flagged.
- Probabilities calibrated by Platt scaling fitted on the validation years only.
- Baselines that must be beaten before the GRU is kept: label persistence, FWI threshold, logistic regression (current day), logistic regression (flattened window), gradient boosting.

## Data (three levels, never mixed in one number)
| Level | What | Status |
|---|---|---|
| S | Synthetic summers with a hazard that depends on a latent fuel moisture (known truth, oracle available) | built here; **proves the code learns memory, not that fires are predictable** |
| A | Algerian Forest Fires data set (2 sites, 244 days of 2012, fire / no fire per day, CC BY 4.0) | built here; tiny, real |
| P | Tunisian / Mediterranean history: Open-Meteo or ERA5 daily weather + NASA FIRMS (VIIRS) hotspots | adapter and download scripts provided |

## Metrics and pass criteria (set before running)
| Check | Criterion |
|---|---|
| numpy GRU vs PyTorch GRU | max abs difference ≤ 1e-5 on 200 random windows |
| Split hygiene | train, validation, test never share a year (S) or a site (A): unit test |
| S: recovery | test AUPRC ≥ 0.90 × oracle AUPRC, and ≥ logistic-on-current-day + 0.02 (memory helps by construction) |
| A: real check (leave-one-site-out, both ways) | AUROC and Brier with 95 % block-bootstrap CI (blocks of 7 days), against the 5 baselines. **The GRU is called better only if the CI of the AUROC difference vs the best baseline excludes 0**; otherwise the conclusion is "no evidence of a difference" |
| Calibration | ECE after Platt ≤ ECE before, on the held-out fold |
| Runtime | one daily update < 1 ms (numpy, host CPU); model file < 20 kB |

## Not done
- Training on Tunisian fire records (level P): needs the PC and the two accounts (FIRMS key, optional ERA5).
- No claim about field performance. A positive result on S or A says nothing about real ignition prediction.

## Known limits
- A satellite hotspot is not an ignition report (overpass times, cloud, small fires missed); labels are noisy.
- Weather at a box is not weather at the fire; wind and rain are simulated in the prototype.
- Day-level labels in A are not "fire starts tomorrow" labels exactly; read the data note in the notebook.
