# Fiche — Gateway fire spread and source localisation

**Runs on:** gateway (CPU, numpy). **Spec:** §6 row 3 ("spread and source localisation, grid, wind, slope"), dashboard isochrones 15 / 30 / 60 min and estimated source.

## Role
1. **Spread**: from an ignition point, wind, slope and the day's ISI, compute the time the fire front reaches every cell of a grid, then the 15 / 30 / 60 min isochrones.
2. **Source**: from the gas readings of the boxes and the wind, compute a probability map of where the smoke comes from.

## Input
Grid (cell 10 to 30 m): elevation, fuel factor; wind speed and direction; ISI (from the FWI engine); ignition point (spread); gas depth of each box (source).

## Output
Arrival-time map, isochrone masks; source posterior map, most likely cell, 50 % and 90 % credible area, bearing from each box.

## Design
- Rate of spread of the head fire from ISI with the Canadian form `R = a (1 - exp(-b ISI))^c`, times a slope factor; fuel parameters use default values, to be calibrated on Mediterranean fuels.
- Elliptical front: length-to-breadth ratio from wind speed; ellipse with the ignition at its focus (derived in the notebook); head and back rates follow.
- Arrival times by shortest-path over a 16-neighbour graph (Dijkstra), edge time = distance / rate in that direction.
- Smoke: steady Gaussian plume (Briggs rural, neutral), receptor gas depth taken proportional to concentration (unit-free).
- Source: grid search, intensity profiled out, lognormal noise; also uses "clean" boxes (a silent box downwind is evidence).

## Metrics and pass criteria (set before running)
| Check | Criterion |
|---|---|
| No wind, flat, uniform fuel | mean error of arrival time vs analytic circle ≤ 4 % (16 neighbours) |
| Wind | head and back distances within 5 % of the analytic ellipse; L/B within 8 % |
| Monotonic physics | rate increases with ISI; uphill faster than downhill; isochrones nested |
| Runtime | 100 × 100 grid < 1 s on the host (spec target) |
| Plume | crosswind-integrated flux at 1, 2, 4 km = Q / u within 2 % |
| Source, synthetic, lognormal noise σ = 0.3 | with 4 boxes: MAP within 500 m in ≥ 70 % of 200 trials; median 90 % credible area **decreases** as boxes go 2 → 3 → 4 → 6 |

## Not done
- No real fire, no real plume, no real terrain or fuel map: everything is simulated and flagged as such.
- No fuel-model calibration; no spotting; no suppression; smouldering plumes have little buoyancy and the model ignores plume rise.

## Known limits
- With 2 boxes, the source is **ambiguous** (3 unknowns, 2 numbers): the posterior is a curve, not a point. The output says so (credible area) instead of giving a false point.
- Steady plume assumes constant wind over the travel time.
