# Gateway AI

| Path | Blocks | Phase (spec §6) |
|---|---|---|
| fast path | Cross-box fusion (Bayesian + SPRT, FWI prior), alert level L1 to L5, reason codes | A |
| slow path | FWI forecast 1 to 3 days (gradient boosting) | A |
| slow path | Spread and source localisation (grid, wind, slope) | A |
| slow path | Gas temporal model (1D-CNN or GRU), anomaly autoencoder, larger gas classifier | B |
| camera path | Vision check: the gateway CNN that decides fire / smoke / background from the box photo (`vision/`) | service and training pipeline |
| slow path | Vision re-check (YOLO-nano class, D-Fire), optional | C |

The fast path never waits for the slow path. Each block gets a fiche before code.
