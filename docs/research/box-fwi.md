# Box FWI engine

Code: `ai-data/box/fwi/`. Fiche: `ai-data/box/fwi/FICHE.md`. Reference: xclim 1.0.0 (`xclim.compute.cffwis_indices`).

## RES-FWI-1 · Does the daily chain match a reference implementation? (9 Nov)
- **Question:** do my FFMC, DMC, DC, ISI, BUI and FWI equal the xclim reference on daily noon data?
- **Method:** 4 seasons run through xclim (lat 35°N, start-up FFMC 85 / DMC 6 / DC 15, no fire-season mask, no overwintering): 3 synthetic summers (120, 120, 100 days) and one edge-case season (120 days: -3 °C, 45 °C, 6 % and 100 % RH, calm air and 70 km/h wind, rain of 0.3 to 120 mm). Inputs rounded to 3 decimals so that the stored inputs are the ones xclim saw. Test: `tests/test_codes.py`, threshold 1e-3.
- **Result:** 44 tests pass, 24 of them the comparison (6 components × 4 seasons, 460 days). Largest difference on every component: 5e-7, which is the 6-decimal rounding of the reference file. Criterion was 1e-3.
- **Reading:** the box reproduces xclim on synthetic weather. It does not prove the index fits Tunisian fuels: it is a relative danger scale.
- **Failed attempts (kept):**
  1. First DMC had a constant 100 times too large (`1e-4` written instead of `1e-6` in `K`): caught by a smoke run (DMC 1362 after 2 days), not by a test.
  2. DMC rain branch written with the 1987 paper form `20 + exp(5.6348 - P0/43.43)`: xclim (and the cffdrs package) use `20 + 280 / exp(0.023 P0)`. They differ by about 0.004 on rain days. The CFS form is adopted, as the reference.
  3. First reference file was generated with unrounded inputs while the stored ones were rounded: 17 false failures of about 1e-3. The commit of the corrected file also silently did not overwrite the old one at first; found by comparing checksums.
- **Decision:** daily chain kept as is. **Status:** kept. **Evidence:** `tests/test_codes.py`, `tests/data/fwi_xclim_reference.json`.
- **Day-length tables:** xclim uses the 46°N table for every latitude from 30°N to 90°N. The box does the same. At 33 to 37°N the true day length differs: a latitude-specific table is a refinement, open.

## RES-FWI-2 · Hourly FFMC (9 Nov)
- **Question:** the spec says FWI is hourly on the box. The standard FWI is daily. What is computed each hour?
- **Method:** hourly FFMC of Van Wagner 1977 as published in the `cffdrs` package (rate factor 0.0579 per hour, any rain counts, 147.27723 for the moisture conversion). Constants read from the package source through its documentation page. DMC and DC move once a day, at local noon, with the 24 h rain and the noon observation. ISI, BUI and FWI are recomputed each hour.
- **Result:** physical tests pass: bounds 0 to 101, dries when hot / dry / windy, wets when cool and humid, rain lowers it, 24 hours of hourly steps move the same way as one daily step.
- **Reading:** **no numeric reference run** was possible (R and `cffdrs` are not available here). The hourly equations are checked against their published constants and against physics only. Honest status: not validated numerically.
- **Decision:** keep, flagged as unvalidated. To close: run the R package on the same weather, or compare with a published hourly series. **Status:** open.

## RES-FWI-3 · Does a hot dry spell reach Alert and does rain bring Eco back? (9 Nov)
- **Question:** does the engine switch the box mode in the way the spec describes (Eco below `high`, Alert from `high`)?
- **Method:** `tests/test_engine.py`: 10 days of 36 °C / 18 % RH by day and 25 °C / 50 % by night, 20 km/h, no rain; then 3 days of rain at 15 °C and 98 % RH.
- **Result:** Alert after the dry spell; Eco after the rain. EFFIS class boundaries (5.2 / 11.2 / 21.3 / 38 / 50) tested at each edge.
- **Reading:** a unit-level behaviour check on invented weather, not a validation on Tunisian data.
- **Decision:** kept. **Status:** kept.

## RES-FWI-4 · C port for the ESP32, with saved state and first-24 h defaults (10 Nov)
- **Question:** can the FWI run on the ESP32 with the same numbers as the Python reference, take sensor and time inputs, keep the 24 h rain history in flash, and behave sensibly during the first 24 h?
- **Method:** `ai-data/box/fwi/c/` (C99, no heap). Inputs: hour, month, T, RH, wind, rain per call. State = three codes + 24-slot rain ring, written to storage every hour as a 228-byte CRC32 blob and restored at boot. Defaults for the first start: FFMC 85, DMC 6, DC 15, rain 0 mm/h; `provisional` flag until 24 real hours are recorded. Tests: 203 checks in C (defaults, window, noon-only DMC/DC, round trip, corrupted blob, write failure, bad input) and 8 parity tests in Python against the reference.
- **Result:** C and Python give identical numbers on 2 years of synthetic hourly weather (17 520 h, all six danger classes reached): max abs difference measured 0.0. Same on an extreme sequence (-30 to 45 °C, RH 0 to 100 %, wind 0 to 120 km/h, rain up to 60 mm/h). Daily chain against xclim: 5.0e-7 (criterion 1e-3). A restart at an arbitrary hour (with rain in the window) gives exactly the same outputs as no restart. Damaged flash (flipped byte at 6 positions, truncated blob) falls back to the defaults. A NaN, a negative RH or an hour of 24 is refused and the state is unchanged.
- **Reading:** the port is as correct as the Python reference, no more: the **hourly FFMC is still not validated against cffdrs** (RES-FWI-2). The 0.0 difference is partly because both run on the same libm; on the ESP32's libm, differences of the order of 1e-15 are expected. The flash adapter (`esp32/fwi_nvs.c`) is not compiled and nothing was measured on a board (time, memory).
- **Decision:** keep Python as the reference and the C code as the firmware version; any change goes in both and must keep the parity tests green. Default rain of 0 mm is a choice (danger not underestimated, overestimated after rain). **Status:** kept; hardware test open.

## Not done yet
- Numeric reference for the hourly FFMC.
- Build and run `c/esp32/fwi_nvs.c` and the engine on a real ESP32 (flash write, timing, memory).
- Detection of a gap in time after a reboot (hours the box was off are missing from the 24 h history).
- Latitude-specific day-length tables for 33 to 37°N.
- Real weather: the box measures T and RH (BME680, compensation still to calibrate, RES-GAS-2); wind and rain are simulated in the prototype.
- Real Tunisian fire history to check that the thresholds mean something (open question from the previous work).
