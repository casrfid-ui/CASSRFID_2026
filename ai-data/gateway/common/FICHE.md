# Fiche — Shared gateway tools (`gw_common`)

Small, dependency-light code reused by the gateway prediction blocks.
- `metrics.py`: ROC AUC, average precision, Brier, ECE, Platt calibration, **block bootstrap** confidence intervals (blocks of consecutive days or groups of samples), false alarms at a fixed recall.
- `gru.py`: numpy GRU + dense layers in the PyTorch weight layout (the gateway has no torch); `.npz` read and write.
- `graph.py`: numpy message-passing layer (neighbour features between boxes).

Tested against PyTorch where torch is installed (tests skipped otherwise).
- `weather.py`: synthetic Mediterranean noon weather (assumptions only, not a climate fit).
- `train_gru.py`: generic PyTorch GRU trainer (PC only; imports torch lazily).
