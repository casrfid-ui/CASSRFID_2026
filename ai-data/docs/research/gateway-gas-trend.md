# Research log — gateway block `gas_trend` (early warning from the box's gas-chain outputs)

Fiche (criteria first): `ai-data/gateway/gas_trend/FICHE.md`. Code: `.../gas_trend/python/`. Notebooks: `python/notebooks/`.
Data: real BME688/690 recordings (Mendeley Data, CC BY 4.0), 38 episodes, 13 097 scans, 5 nodes, 2 burns. No synthetic smoke.

## RES-GAST-1 — Setup
- Target: onset (first phase-2 scan) within the next 8 scans; 3 102 windows of 12 scans, 304 positives (9.8 %). Scans from the chain's warm-up excluded; scans at/after onset excluded.
- Leave-one-node-out; validation = next node (cyclic). Thresholds chosen on validation so clean-air flags ≤ the chain's false-smoke rate; evaluated on the test node.
- Models: chain depth (threshold), slope rule, logistic regression (window features), GRU (hidden 12, 769 parameters, 3 seeds, best on validation AP).
- Chain alarm comes a **median of 189 s after the onset** (38/38 episodes alarm): that is the room an early warning can use.

## RES-GAST-2 — Unit-test criteria — PASSED
numpy GRU vs PyTorch ≤ 1e-5; node never shared between train/validation/test; threshold respects the budget; predictor = numpy forward (1e-12); samples exclude warm-up and post-onset scans; update time < 1 ms (unit test).

## RES-GAST-3 — Lead time and false alarms (3 dilution factors; episodes = 38; median lead, missed = 0 s; CI = bootstrap over recordings)

| factor | model | median lead (s) | 95 % CI | missed |
|---|---|---|---|---|
| 1.0 | chain depth | 0 | [0, 776] | 25/38 |
| 1.0 | slope rule | 0 | [0, 776] | 25 |
| 1.0 | logistic | 0 | [0, 978] | 21 |
| 1.0 | GRU | 0 | [0, 0] | 31 |
| 0.5 | logistic | 99 | [0, 1024] | 19 |
| 0.5 | GRU | 0 | [0, 0] | 28 |
| 0.25 | slope rule | 162 | [0, 984] | 19 |
| 0.25 | logistic | 428 | [0, 1232] | 18 |
| 0.25 | GRU | 520 | [0, 1041] | 18 |

- **Every confidence interval includes 0** → conclusion per the fiche: **no earlier than the chain** with this data.
- **False-alarm criterion NOT met on several test nodes.** Chain false-smoke rate is 0/h on nodes 1, 2, 4, 5 and 9/h on node 3 (factor 1). Flags/h on clean air at factor 1: threshold models 118/h on node 1 (the 2021 burn, other sensor baseline), 14/h on node 3; logistic 65/h (node 1), 21/h (node 4); GRU 17.6/h (node 3), 2.9/h (node 4). At factor 0.5/0.25, GRU and logistic exceed 100/h on node 4. A lead time bought this way is not usable.
- Window-level ranking is unstable across nodes: GRU AUROC 0.90 / 0.84 / 0.62 / 0.36 / 0.17 on nodes 1–5 (anti-predictive on 4 and 5); logistic 0.71 / 0.63 / 0.25 / 0.80 / 0.60; positive rate 0.098.
- A first run with 2 GRU seeds gave different per-node false-alarm values (GRU 1.2 / 0 / 23.7 / 0 / 0 per hour instead of 0 / 0 / 17.6 / 2.9 / 0): the conclusions above do not depend on a particular seed, the numbers do.

## Interpretation
- The signal before the onset is small, and node-to-node baseline differences (and different heater profiles/scan periods) dominate. 4 training nodes cannot teach a model what "just before onset" looks like in a new node.
- The apparent gain at factor 0.25 (more leads) comes with false alarms and wide intervals; with strongly diluted smoke the chain itself is late, so the potential room is larger — **but nothing here demonstrates that the model realises it.**

## Not done / limits
- Only 2 burns; the 2 sensors per file are near-duplicates (blocks are recordings, not scans). Indoor-style burns, no Tunisian fuel, no slow smouldering on forest fuel; dilution is a linear stand-in.
- The demo model (`models/gas_trend_demo.npz`, 769 parameters, 9 KB) is trained on nodes 1–4 and thresholded on node 5: **no held-out evidence**; it exists to exercise the gateway code path.

## What may be claimed
The block is implemented, tested, cheap (< 1 ms) and honestly evaluated; **it is not shown to warn earlier than the box's chain.** For the report: present as a negative/neutral result with the method, not as a feature.
