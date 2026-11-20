# Fiche — Gateway gas trend model (early warning, GRU)

**Runs on:** gateway, background. **Spec:** §6 row 4 ("gas temporal model, catch slow smouldering"), phase B. **Inputs come from:** `../../box/gas_chain` (per-scan result sent in the frame).

## Role
Tells, from the last scans of one box, the probability that a smoke onset will be reached within the next H scans, so that a slow rise is flagged **before** the box's own threshold is crossed. The box class and alert stay those of the gas chain.

## Input (one row per scan, from the frame)
`score, depth, band1, band2, band3, temp_c, rh_pct` (7 features), window 12 scans, scans from the chain after warm-up.

## Output
`p_onset` (within H scans), `lead_hint` (scans), and a flag `early` when `p_onset` exceeds the threshold chosen for the false-alarm budget.

## Design
- Target: onset = first scan of the first phase with a response (phase 2 of the data set); label 1 for the H scans before it, 0 before that; scans after onset are excluded (the chain handles them).
- Models: threshold on depth (the chain), slope rule (extrapolate depth), logistic regression on window features, GRU (hidden 12).
- Threshold of the early flag chosen on validation to match the chain's false-alarm rate on clean air (equal-budget comparison).
- Distance proxy: the chain's `dilute` function (RES-GAS), factors 1.0, 0.5, 0.25.

## Data
Real BME688/690 recordings (20 files, 5 nodes, 2 burns: 2021 node 1; 2025 nodes 2 to 5). Split **by node** (leave-one-node-out); the burn is the group for the report. No synthetic smoke.

## Metrics and pass criteria (set before running)
| Check | Criterion |
|---|---|
| numpy GRU vs PyTorch | max abs difference ≤ 1e-5 |
| Split hygiene | a node is never in train and test: unit test |
| False alarms | at the chosen threshold, false early flags per hour of clean air ≤ the chain's false smoke rate on the same fold |
| Lead time | median (flag time − chain alarm time) in seconds, with bootstrap 95 % CI, per dilution factor. **Reported, no pass level**: if the CI includes 0 the conclusion is "no earlier than the chain" |
| Missed onsets | share of onsets with no flag before the chain alarm, reported |
| Runtime | one update < 1 ms |

## Not done
- No recording of a slow smouldering fire on a Tunisian fuel; the 5 nodes are indoor-style burns of the data set authors.
- No fire phase labels beyond the authors' (phases are numbered by order, tags undocumented).

## Known limits
- Learning to anticipate the chain on 4 recordings per node is a small-sample problem; the intervals will be wide.
- Sensor drift over weeks and humidity artefacts are only partly in the data.
