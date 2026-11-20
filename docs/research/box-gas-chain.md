# Box gas chain

Code: `ai-data/box/gas_chain/python/`. Fiche: `ai-data/box/gas_chain/FICHE.md`. Notebook: `ai-data/box/gas_chain/python/notebooks/01_real_data_evaluation.ipynb`.
Data: Mendeley "Dataset Smoke Detection" (BME688/690, 2 burns, 38 episodes, 13 097 scans), CC BY 4.0. Split by burn (2021, 2025).

## RES-GAS-1 · Does the chain meet the fiche criteria on real smoke? (6 Nov)
- **Question:** with default settings, are false smoke, recall and fault share inside the fiche limits?
- **Method:** `replay(load_all())`, one fresh chain per episode (38). Clean = phase 0, strong smoke = phases 3 to 5.
- **Result:**

| Burn | False smoke (clean) | Recall (strong) | Fault in strong | Delay from phase 2 |
|---|---|---|---|---|
| 2021 (8 episodes) | 0.0 % | 1.000 | 0.0 % | 3.1 min |
| 2025 (30 episodes) | 1.9 % | 1.000 | 0.0 % | 3.2 min |

- **Reading:** 6 of 6 criteria pass. All false smoke comes from 4 episodes (node 3, profiles 2 and 3: scans every 77 to 111 s, 7 to 15 clean scans). Without them, 0. The 2% limit is passed by 0.1 point.
- **Carried over:** gas limit 120 MΩ (BME688 saturates at 102.4 MΩ and that reading is valid) comes from the old log (NOD-2), where 22 % of scans were wrongly faulted. Re-tested only by a unit test, not re-measured.
- **Does not prove:** anything on the BME680, decoys, or other fuels and distances.
- **Decision:** defaults kept. **Status:** kept. **Evidence:** notebook, `tests/test_real_data.py`.

## RES-GAS-2 · Can T/RH compensation be fitted on clean air? (6 Nov)
- **Question:** the spec makes T/RH compensation mandatory. Can `a_t`, `b_h` be fitted on the clean start of each burn?
- **Method:** least squares of ln R on T and RH, centred per episode and heater step, phase 0 only. Fit on one burn, judge on the other.
- **Result:** `a_t` = -0.143 (2021, R2 0.35) and -0.132 (2025, R2 0.06). `b_h` = -0.003 and -0.110. Fitted on 2025 and judged on 2021: false smoke 25.4 % (was 0.0 %). Fitted on 2021 and judged on 2025: false smoke 1.2 % (was 1.9 %), delay 6.8 min (was 3.2), recall 0.993.
- **Reading:** the fit does not transfer. Clean-air temperature moves with sensor settling after power-on, so the coefficient mixes two effects. The previous tree's constants (`a_t` -0.012, `b_h` -0.006) were tuned on a simulator and are not used.
- **Decision:** `a_t = b_h = 0`. Stage kept. Needs a controlled T/RH sweep on the own BME680. **Status:** open (failed attempt kept).
- **Evidence:** notebook, `evaluate.fit_compensation`.

## RES-GAS-3 · Do a longer burn-in or warm-up cure the power-on drift? (6 Nov)
- **Question:** the previous plan was "longer conditioning after power-on". Does it help?
- **Method:** grid burn-in 0, 6, 12, 24 scans × warm-up 6, 12 scans.
- **Result:** false smoke 2021 from 0.0 % (6/6) to 5.0 % (24/6). 2025 from 0.3 % (6/12) to 3.6 % (24/6). No setting is best in both burns.
- **Reading:** noise level of this sample (few clean scans per episode). No evidence for a longer conditioning.
- **Decision:** keep burn-in 6, warm-up 6. **Status:** kept. The remaining lever is a baseline saved in flash, to test in the field.

## RES-GAS-4 · How much slow drift can baseline + CUSUM tolerate? (6 Nov)
- **Question:** when does a slow drift of clean air become "smoke"?
- **Method:** synthetic sensor (`tests/test_chain.py`): drift of ln R per scan at 30 s scans.
- **Result:** 0.0036 ln/h is followed by the baseline and never called smoke. 0.012 ln/h is called smoke.
- **Reading:** by construction the tolerated rate is about `cusum_k / tau_base` = 0.03 / 6 h = 0.005 ln/h. The real BME680 drift rate is unknown.
- **Decision:** keep the constants as provisional; measure drift over days on the own sensor. **Status:** open. **Evidence:** the two drift tests.

## RES-GAS-5 · What does the median of 5 cost? (6 Nov)
- **Question:** the spec asks for a median of 5 scans. What is the price in delay?
- **Method:** median window 1, 3, 5, both burns, delay counted from the first phase with a response (phase 2).
- **Result:** delay 2.0 / 2.6 / 3.1 min (2021) and 2.2 / 2.6 / 3.2 min (2025). Recall 1.000 throughout. False smoke 2.9 / 1.6 / 0.0 % (2021) and 1.8 / 2.0 / 1.9 % (2025).
- **Reading:** about 1 minute more at 25 to 27 s per scan, for the same recall. The effect on false smoke is within noise.
- **Decision:** keep 5. **Open:** at Eco cadence (300 s) the window spans 25 min, and it still holds Eco scans after a switch to Alert. Flush or shrink on mode change (to decide with the state machine). **Status:** kept / open.

## RES-GAS-6 · How far does the chain see, as the smoke gets weaker? (6 Nov)
- **Question:** how does recall fall when the response is diluted (stand-in for distance)?
- **Method:** semi-synthetic. ln R drop vs the clean start is multiplied by a factor; scan-to-scan sensor noise is added back so noise does not shrink with the signal. Truth: strong phase and response ≥ 0.1 ln R.
- **Result:** the recorded response is large (median 3.57 ln R, 5th percentile 1.36). Recall at factors 1 / 0.5 / 0.25 / 0.12 / 0.06 / 0.03: 2021 1.000 throughout; 2025 1.000 / 1.000 / 0.999 / 0.995 / 0.986 / 0.944.
- **Reading:** optimistic. Linear scaling, one fuel, one site, no other gases in a distant plume. The previous log (NOD-4) found earlier loss of recall under another truth rule; not reproduced, not comparable.
- **Decision:** make no distance claim. Measure with own recordings at several distances. **Status:** open.
- **Failed attempts:** (1) dilution without noise add-back: the sensor noise shrank with the signal, recall looked too good. (2) noise taken as the std of the clean phase: it includes drift, so false smoke rose to 15.7 % at factor 0.12. Replaced by scan-to-scan noise (differences, drift removed).

## RES-GAS-7 · Each stage as a pure function (10 Nov)
- **Question:** can every stage be developed, tested and later ported to C on its own?
- **Method:** the baseline rules (learning gate, freeze rule, follow), the spike test and the class debounce were extracted from `chain.py` into `stages.py`; `tests/test_stages.py` tests the seven stages alone (36 tests). Before and after, the chain was run on the 1798-scan real sample plus one sequence with injected faults (out-of-range burst, 15 identical scans, one spike, slow drift): 2168 scans, every output field compared.
- **Result:** outputs identical (every field of every scan). Full suite: 54 tests pass.
- **Reading:** a refactor, not a new result. It proves the behaviour did not move, and gives the C port a function-by-function target.
- **Decision:** kept. **Status:** kept.
- **Fact recorded:** in the real data one scan (10 steps) lasts about 27 s (median scan period 27 s, p10 25 s, p90 37 s, max 78 s). All counts in scans (median of 5, 2 scans to confirm, 3 to release, 12-scan warm-up) are therefore seconds-to-minutes at that pace, and **about an hour for the warm-up at Eco pace (300 s)**. The 3.1 min delay was measured at the 27 s pace, not at 300 s.

## RES-GAS-8 · Does a false alarm recover? What do the 4 failing episodes have in common? (10 Nov)
- **Question:** RES-GAS-1 scored phase 0 only. What happens in phase 1 (no physical response) after a false smoke, and is the failure explained by the scan period or the clean-start length alone?
- **Method:** `notebooks/01_real_data_evaluation.ipynb`, section 4: per-episode table (clean scans scored, scan period, false rate), smoke calls in phase 1, internals of one failing episode (node 3) against a normal one (node 2), share of scans with steps 0 and 1 at the sensor saturation (102.4 MOhm).
- **Result:**
  - Only **30 of 38 episodes** have clean scans left after the warm-up; 8 episodes of 2025 are not evaluable on clean air. The 2025 figure (1.9 %) is 4 failing episodes out of **22** scored.
  - In the 4 failing episodes (node 3) the false alarm **latches**: 35 of 35 scans of phase 1 are called smoke while the physical response is about zero. Phase 1 smoke share: 0.0 % (2021), 4.1 % (2025). A fifth episode has 3 calls with a response up to 0.41 ln (possibly real).
  - Mechanism seen on the plots: the sensor starts far from its operating point (step 8 falls from about 14 to 11 ln within about 10 min), the baseline is learned on the tail of that transient and the signal settles about 0.25 ln lower; the baseline follows only about 0.4 % of a gap per 77 s scan; the CUSUM (k 0.03) builds up; the class turns to smoke; the baseline is then frozen and nothing corrects it.
  - All 26 other scored episodes have at least 23 clean scans and a scan period of at most 38 s. The 4 failing ones have 7 to 15 clean scans and 77 to 111 s.
  - Saturation of steps 0 and 1 (95 to 96 % of clean scans in the failing episodes) also occurs in 11 of the 26 other scored episodes (up to 87 %) without false smoke: it does not explain the failure by itself.
- **Reading:** a correlation on 4 episodes of one node, not a demonstrated cause (one node, one scan period, a short clean start and one sensor come together). The freeze that protects a real fire from being absorbed also blocks recovery from a false alarm.
- **Decision:** defaults kept; the latching is recorded as a design weakness. Remedies **not tried**: release after a long quiet period, baseline saved in flash, longer warm-up for slow scans, fusion on the gateway. **Status:** open.

## RES-GAS-9 · Does the C port give the same numbers as the Python reference? (10 Nov)
- **Question:** the ESP32 runs C. Is the C chain the same function as the Python one?
- **Method:** `ai-data/box/gas_chain/c/` (one file per stage), host build with `-Wall -Wextra -Wpedantic`. `python/tests/test_c_parity.py` feeds the same scans to both and compares every output field per scan (tolerance 1e-9, class / flags / step exact): every episode of the real sample (BME688), one episode with injected faults (out-of-range burst, 15 stuck scans, lone spike, slow drift, a NaN reading, temperature and humidity out of range), a restore from a saved baseline, irregular time steps (27.3 / 30 / 300 / 3600 s). Unit tests: 2060 checks, every stage alone.
- **Result:** all pass. First write of the C unit tests had 14 failures, all wrong expectations in the tests (band mean of steps 4 to 6 is 6 not 5; the median of 5 delays the first smoke call by a few scans; a spike of 1.0 ln is below the 1.5 flag; 12 identical scans need 13 calls; the baseline moves a little before the smoke call), none in the library. One real divergence found while writing the port: Python let a NaN reading through to `log` (all comparisons with NaN are false); both languages now treat a non-finite value as a range fault.
- **Reading:** parity proves the port, not the model: BME680 and the Eco pace are still not validated (RES-GAS-1 limits stand). Doubles are used on purpose; a single-precision build was not tried.
- **Decision:** kept. **Status:** kept. **Evidence:** `ai-data/box/gas_chain/c/test/`, `python/tests/test_c_parity.py`.

## Not done yet
- Test remedies for the latching false alarm (RES-GAS-8).
- Delay and recall at the Eco pace (300 s): sub-sample the real scans to that rate.
- Plausible range of the BME680 gas resistance (the 120 MOhm upper bound comes from the BME688 saturation).
- Own BME680 recordings (incense, smouldering wood, indoors), including decoys and a T/RH sweep.
- Heater profile of the BME680 (10 forced measurements, temperatures to choose) and the 3-band split on it.
- Frame fields (score byte, class, flags).
- Eco → Alert window flush; baseline restore in the field.
