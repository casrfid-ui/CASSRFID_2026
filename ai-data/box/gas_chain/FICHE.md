# Fiche — Box gas chain

**Runs on:** Box (ESP32-CAM). **Spec:** section 5.1, figure 2, section 5.4.
**Python reference:** `python/` (one pure function per stage in `src/gas_chain/stages.py`, tests in `python/tests/`). **C port for the ESP32:** `c/` (one file per stage, `src/gc_*.c`; checked against the Python reference scan by scan).

## Role
60 raw values (10 heater steps × gas, T, RH) become **one score, one class, one set of flags**.

## Input (one scan)
| Field | Unit | Note |
|---|---|---|
| `gas[10]` | ohm | BME680 forced mode, one forced measurement per heater temperature |
| `temp[10]` | °C | sensor temperature, self-heating offset calibrated (`t_offset_c`) |
| `rh[10]` | % | |
| `dt_s` | s | time since the previous scan (Eco 300 s, Alert 30 s). In the real data one scan lasts about 27 s |

## Output
| Field | Meaning |
|---|---|
| `score` | 0..1, max(instant, CUSUM) |
| `cls` | normal / smoke / decoy / sensor_fault |
| `faults` | bit mask: range, stuck, spike (spike is informational) |
| `bands[3]` | depth in ln units: low, mid, high heater temperature |
| `warmup` | true while the baseline is not ready (no class is trusted) |

## Stages
| # | Stage | Rule |
|---|---|---|
Order of execution in the code (spec numbering in brackets). Compensation runs before the filter so that the filter works on the quantity the baseline is built on.

| # | Stage | Rule |
|---|---|---|
| 1 [2] | Quality check | range, stuck value (identical scans), spike flag. A bad scan never enters the state |
| 2 [4] | T/RH compensation | `ln R − a_t·(T−25) − b_h·(RH−50)`; `a_t = b_h = 0` (the fit does not transfer between burns, RES-GAS-2) |
| 3 [3] | Filter | median of 5 scans per step, then exponential smoothing (0.35) |
| 4 [5] | Baseline | burn-in 6 scans, warm-up 6 scans, then slow follow (tau 6 h); **frozen** during an anomaly; saved/restored (flash) |
| 5 [6] | Depth bands | 3 bands over the 10 steps |
| 6 [7] | Score | instant (depth / 0.30) and CUSUM, score = max |
| 7 [7] | Class | thresholds 0.40 / 0.20 with hysteresis, then debounce (2 scans to enter, 3 to leave, fault at once). Decoy off until real decoy data exists |

## Demonstration
`python/notebooks/02_stage_by_stage_demo.ipynb`: each stage with its equation, run on the real sample, with figures (English, stored outputs). `01_real_data_evaluation.ipynb`: full-set evaluation.

## Target sensor: BME680
- The data set was recorded with BME688/690. The box uses a **BME680**: it has no hardware sequence, so the firmware runs the 10 forced measurements one by one (heater temperature and duration per step to define).
- Settings that come from BME688/690 data and must be re-checked on the BME680: gas upper bound (120 MOhm, from the BME688 saturation), depth scale 0.30, thresholds 0.40 / 0.20, CUSUM (k 0.03, h 1.0), burn-in and warm-up counts.

## Data
- **Mendeley "Dataset Smoke Detection"** (BME688/690, 2 burns, CC BY 4.0): replay and cross-check. Not the target sensor.
- **Own BME680 recordings** (incense, smouldering wood, indoors): **required** before any claim on the real sensor.

## Metrics and pass criteria (provisional, set before looking at the final numbers)
| Metric | Criterion |
|---|---|
| False smoke on clean air (phase 0, after warm-up) | ≤ 2 % of scans, both burns |
| Recall in strong smoke (phases 3–5) | ≥ 0.95, both burns |
| Sensor fault flagged inside strong smoke | ≤ 1 % of scans |
| Time to first smoke after the burn starts | reported, no threshold |
| Sensitivity vs dilution (distance proxy) | curve reported, no threshold |

## Known limits
- Heater temperatures of the Mendeley profiles are undocumented; band split is by step order.
- Decoy class cannot be validated: no real decoy data.
- Two burns, one site type, one fuel family, ~100 m.

## C port (ESP32)
| Python (`stages.py`, `chain.py`) | C (`c/src/`) |
|---|---|
| `quality_flags` | `gc_quality.c` |
| `compensate` | `gc_compensate.c` |
| `window_median`, `is_spike`, `smooth` | `gc_filter.c` |
| `learning_gate`, `baseline_may_follow`, `baseline_follow` | `gc_baseline.c` |
| `band_depths`, `instant_score`, `update_cusum` | `gc_score.c` |
| `wanted_class`, `debounce` | `gc_class.c` |
| `GasChain` (`update`, `snapshot`, `restore`) | `gc_chain.c` (`gc_init`, `gc_update`, `gc_snapshot`, `gc_restore`) |
| `Config` | `gc_config.c` (`gc_config_default`, `gc_config_check`) |

C99, no heap, no I/O, doubles, one `gc_chain_t` (1296 bytes on a 64-bit host) per sensor. A non-finite reading (NaN, infinity) is a range fault in both languages. `gc_update` refuses `dt_s <= 0` and leaves the state untouched. Tests: `make test` in `c/` (2060 checks, every stage alone and the chain); parity: `python/tests/test_c_parity.py` (real episodes, injected faults, restore, irregular `dt`), max difference allowed 1e-9, discrete outputs exact.
