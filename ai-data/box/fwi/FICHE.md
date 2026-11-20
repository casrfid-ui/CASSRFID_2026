# Fiche — Box FWI engine

**Runs on:** Box (ESP32-CAM). **Spec:** §5.2, §5.4. The gateway only forecasts 1 to 3 days ahead.
**Python reference:** `python/` (tests, xclim check). **C port for the ESP32:** `c/` (checked against the Python reference).

## Role
Weather in, fire danger out. The danger class sets the **mode** (Eco / Alert) and the **detection thresholds**.

## Input
| Field | Unit | Source |
|---|---|---|
| `temp_c`, `rh_pct` | °C, % | BME680 (outside the enclosure, compensated) |
| `wind_kmh`, `rain_mm` | km/h, mm | **simulated** in the prototype, flagged as simulated in every frame |
| month, latitude | — | fixed at install (GPS) |

## Output
FFMC, DMC, DC, ISI, BUI, FWI, danger class (6 EFFIS classes), mode (`eco` / `alert`), threshold scale.

## Design
- **Daily** codes (DMC, DC, daily FFMC) at local noon: standard Canadian FWI (Van Wagner 1987), 24 h rain.
- **Hourly** FFMC (Van Wagner 1977, as in the `cffdrs` package) so the danger follows the afternoon drying; ISI and FWI each hour from the hourly FFMC and the day's BUI.
- Start-up values: FFMC 85, DMC 6, DC 15, rain 0 mm per hour. They stand in for the first 24 h; the output carries `provisional` until 24 real hours are recorded.
- The three codes and the 24 h rain history are saved to flash every hour and restored at boot (C port, CRC-checked; damaged data falls back to the defaults).

## Metrics and pass criteria (set before running)
| Metric | Criterion |
|---|---|
| Daily FFMC, DMC, DC, ISI, BUI, FWI vs xclim | max abs difference ≤ 1e-3 on 4 seasons, incl. an edge-case season |
| Hourly FFMC | physical checks (bounds, monotonic drying and wetting, rain raises it); **no numeric reference run** — stated as such |
| Class boundaries | EFFIS: 5.2 / 11.2 / 21.3 / 38 / 50 |
| C port vs Python, hourly engine, 2 years synthetic + extremes | same numbers (max abs diff measured 0.0), same class and mode |
| C port daily chain vs xclim | max abs diff ≤ 1e-3 (measured 5.0e-7) |
| C port persistence | restart at any hour gives the same outputs as no restart; damaged flash falls back to defaults |

## Embedded notes
- `c/esp32/fwi_nvs.c` is the flash adapter (ESP-IDF NVS).
- Host build: engine state 228 bytes serialised.

## Known limits
- Rain and wind are simulated in the prototype.
- Tunisian fuels are not Canadian fuels: the index is a relative danger scale, not a calibrated ignition probability.
- Day-length tables depend on latitude (33 to 37 °N here).
