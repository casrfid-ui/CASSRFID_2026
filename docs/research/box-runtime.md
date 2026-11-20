# Box runtime and C ports

Code: `ai-data/box/runtime/` (`c/` ESP32, `python/` reference). Fiche: `ai-data/box/runtime/FICHE.md`.

## RES-RT-1 · Does the chained C runtime equal the three Python blocks chained? (10 Nov)
- **Question:** the box runs FWI (hourly), the gas chain (per scan) and the state machine in one call per wake-up. Does the C runtime give, tick by tick, what the three Python blocks give?
- **Method:** `python/src/box_runtime/runtime.py` chains the Python blocks with the same time rules as the C runtime (no flash). `python/tests/test_c_parity.py` replays the real BME688 sample (1798 scans) with random weather (diurnal and slow cycles, 3 % of wake-ups without weather), rain events, flame, camera results, Survival periods, housing and supply faults, 2 % of wake-ups without a gas scan: (a) at the dataset pace (27 s), 2500 ticks requested (1798 available); (b) at the Eco pace (300 s per scan, about 7 days, 173 FWI hours, noon updates); (c) the same with a UTC+2 offset. Compared per tick: state-machine output and frames, FWI update flag, danger, mode, FWI and the three codes, gas class, score and warm-up. Tolerance 1e-9.
- **Result:** all pass; the replays reach Suspicion. C unit tests (375 checks): one FWI update per local hour, rain accumulated between hours and nothing lost when the weather is invalid, local noon and month change, alert mode after 5 extreme hours, gas to Fire with an alert frame, Survival ignores the gas sensor, flash copies written and restored after a reboot, an FWI hour not applied twice after a reboot, damaged baseline refused, Fire latch survives a reboot until reset, last gasp not repeated after a reboot, flash write failures counted and survived, clock going backwards flagged.
- **Reading:** the Python chain is written by the same hand as the C glue, so parity catches porting errors, not design errors. The replay uses invented weather and invented flame / camera events; the real gas data is BME688 at the dataset pace. Nothing here has run on an ESP32: the NVS adapter, `main.c` and `board.h` were only syntax-checked against stub headers.
- **Decision:** kept. **Status:** kept. **Evidence:** `ai-data/box/runtime/c/test/test_box_runtime.c`, `ai-data/box/runtime/python/tests/test_c_parity.py`.

## Not done yet
- Build and run on the ESP32 (ESP-IDF toolchain, board): NVS adapter, `main.c`, component names, timing and RAM / flash figures.
- Sleep and wake integration (timer plus flame pin), energy per wake-up.
- Frame payload contract with the gateway.
- Flash wear figure on the chosen part.
