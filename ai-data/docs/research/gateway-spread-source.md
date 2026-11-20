# Research log — gateway block `spread_source` (fire spread + smoke source)

Fiche (criteria first): `ai-data/gateway/spread_source/FICHE.md`. Code: `.../spread_source/python/`. Notebooks: `python/notebooks/`.
Everything is simulated; no real fire, plume, terrain or fuel map was used.

## RES-SPREAD-1 — Geometry and numerics (unit tests + notebook 01) — all PASSED
| Criterion | Result |
|---|---|
| No wind, flat: mean arrival-time error vs analytic circle ≤ 4 % | 1.33 % (max 2.75 %) |
| Head and back distance within 5 % of the analytic ellipse | wind 8 km/h: 1250 vs 1254 m, 265 vs 268 m; wind 15 km/h: 1250 vs 1254 m, 90 vs 92 m (grid cell 5 m) |
| L/B within 8 % | 1.32 vs 1.31 (8 km/h); 2.00 vs 1.98 (15 km/h) |
| Monotone physics | rate rises with ISI; uphill 6.3 min vs downhill 62.8 min to 300 m on a slope of 0.4; isochrones nested |
| Runtime 100×100 | 0.04 s |
- These tests verify the **numerics against the model's own equations**. They say nothing about whether the model matches a real fire.
- First version of the ellipse test used a grid only 1000 m wide: the wind-8 ellipse (width ≈ 1150 m) was cut by the grid border and the L/B check failed. Grid enlarged; not a model error.
- Back-distance accuracy needs a fine grid at strong wind (back distance 90 m at 15 km/h = 4 cells of 20 m): with the gateway's planned 20 m cells the back of the fire is resolved to about ±20 m. Irrelevant for alerting, relevant if the test is repeated at 20 m.

## RES-SPREAD-2 — Parameters that are placeholders (not calibrated)
Head rate `45·(1−exp(−0.05·ISI))^1.2` m/min; L/B form and slope form are the Canadian FBP forms recalled from memory and **flagged to verify against the primary reference**; downslope treatment symmetric and clip [0.2, 5] are our assumptions; fuel factor 1 everywhere. A rate of ≈ 21 m/min at ISI 15 is plausible for shrub fuel but unverified.

## RES-SOURCE-1 — Plume maths — PASSED
Crosswind-and-vertical integrated flux / Q = 1.0000 at 1, 2, 4 km (criterion 1 ± 0.02).

## RES-SOURCE-2 — Source localisation, 200 trials per row, lognormal noise σ = 0.3
**Random geometry** (boxes uniform in a 4 × 4 km domain, wind in any direction; source within 1.5 km of the centre):

| boxes | P(≥1 box alarms) | P(≥2 alarm) | success (≤ 500 m) if ≥ 2 alarm |
|---|---|---|---|
| 2 | 0.14 | 0.01 | 0/2 |
| 3 | 0.19 | 0.01 | 1/3 |
| 4 | 0.26 | 0.01 | 2/2 |
| 6 | 0.41 | 0.09 | 0.24 (n = 17) |
| 10 | 0.56 | 0.17 | 0.71 (n = 34) |

**Favourable geometry** (all boxes 0.5–3 km downwind, crosswind offset ≈ N(0, 0.7 σy)) — best case, not typical:

| boxes | success ≤ 500 m | median error | median 90 % credible area |
|---|---|---|---|
| 2 | 0.39 | 767 m | 45.8 km² |
| 3 | 0.65 | 338 m | 40.8 km² |
| 4 | **0.71** | 276 m | 0.72 km² |
| 6 | 0.89 | 151 m | 0.10 km² |

- Criterion "≥ 70 % within 500 m with 4 boxes": **met only in the favourable geometry (0.71, barely)**; **not met with randomly placed boxes**, where the narrow plume (±76 m at 1 km) misses most boxes and a single alarming box cannot localise.
- Criterion "90 % area decreases 2 → 3 → 4 → 6": met in the favourable geometry (45.8 → 40.8 → 0.72 → 0.10 km²); 2 → 3 is a weak decrease.
- Two boxes: ambiguous as predicted (area ≈ 46 km² of 64 km²), and the output reports the area instead of a point.

## Consequences
- With few boxes, the honest output is **the bearing from the alarming box (upwind direction)**, not a source point. A map only from ≥ 3–4 simultaneous alarms.
- Steady narrow plume probably underestimates how often a box is touched (real plumes meander and widen with time averaging and terrain) and overestimates the sharpness of the posterior. Not measured.

## Not done
No fuel calibration, no spotting, no plume rise, no terrain-driven wind, no real data. Integration with the other boxes' gas readings (units!) is for the integration phase.
