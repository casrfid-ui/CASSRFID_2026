# Box state machine

Code: `ai-data/box/state_machine/python/` (reference) and `ai-data/box/state_machine/c/` (ESP32). Fiche: `ai-data/box/state_machine/FICHE.md`. Notebook: `ai-data/box/state_machine/python/notebooks/01_wake_rate_on_real_data.ipynb`.

## RES-SM-1 · Do the spec rules hold as a machine? (9 Nov)
- **Question:** do the rules of spec figure 3 and table 7.2 produce a coherent machine, without the gateway?
- **Method:** 18 unit tests, one per rule: modes and scan intervals, flame debounce (2 reads), camera confirmation (threshold 0.6), gas + flame agreement, Fire latch and hold, clear counter, camera wake period, pump pre-wetting, last-gasp frame once, Survival, frames only on change or heartbeat.
- **Result:** 18 pass. Gas alone or flame alone, however long, never reaches Fire; a second witness (camera, or gas + flame) is needed.
- **Reading:** the machine does what the fiche says. The fiche values (2 flame reads, 10 clear scans, 30 min hold, 0.6 confidence, 30 s camera period) are my assumptions from the spec text, not measurements.
- **Assumptions to confirm with the team:** (1) Survival mode keeps the flame sensor as a hardware wake source; (2) pump pre-wetting from FWI class 'high' plus Suspicion (the spec's default for open decision 2); (3) a camera result of `smoke` above the threshold counts as "camera confirms".
- **Decision:** kept. **Status:** kept. **Evidence:** `tests/test_machine.py`.

## RES-SM-2 · How often does real gas data wake the camera, and how fast does it reach Suspicion? (9 Nov)
- **Question:** the gas chain drives the machine. What is the camera wake rate in clean air, and the delay in real burns?
- **Method:** Mendeley, 38 episodes. Gas chain (default) → machine, scan by scan. No flame, no camera result. FWI forced to 'high' (worst case for wakes and pump).
- **Result:**
  - Clean air, 13.13 h: 4 entries into Suspicion (0.3 per hour), 28 camera wakes (2.1 per hour), 5.3 % of the time in Suspicion. All come from the 4 node-3 episodes of RES-GAS-1.
  - Burns: 38 of 38 episodes reach Suspicion, median 3.1 min after the start of phase 2 (90th percentile 7.5, max 7.9).
  - Strong smoke, 37.37 h: 3111 camera wakes, 83 per hour.
- **Reading:** the machine adds no delay beyond the gas chain. Wake counts are an average that hides a concentration in the drifting episodes. Energy per capture is unknown. Two burns, BME688, gas only.
- **Decision:** no change to the machine yet. **Open:** after a confident `background` camera result, back off the wake period; after a first camera result, lengthen the period. Both to decide once the CNN exists and a capture has an energy figure. **Status:** open.
- **Evidence:** notebook.

## RES-SM-3 · Does the C port take the same decisions as the Python reference? (10 Nov)
- **Question:** the box runs C. Does `sm_step` decide exactly like `StateMachine.step`?
- **Method:** `ai-data/box/state_machine/c/`. 556 C checks (the 18 cases of RES-SM-1, plus bad arguments, unknown camera label, frame overflow). `python/tests/test_c_parity.py`: 4 random streams of 6000 steps (burst-structured gas, flame, camera results with labels and confidences around the 0.6 threshold, FWI mode and danger, Survival, housing and supply faults, operator resets, dt from 10 s to 3600 s), compared on state, interval, camera, GPS, pump, reason bits, last gasp and every frame.
- **Result:** all identical; every stream visits Normal, Suspicion and Fire. The folder was reorganised to `python/` + `c/` (notebook paths fixed, notebook re-run OK).
- **Reading:** parity says nothing new about the thresholds, which are still assumptions (RES-SM-1).
- **Decision:** kept. **Status:** kept. **Evidence:** `c/test/`, `python/tests/test_c_parity.py`.

## RES-SM-4 · Shorten the wait for the second flame read (12 Nov)
- **Question:** RES-FL-1 showed that a real flame takes 5 to 10 min in Eco to open a suspicion, because two consecutive positive wake-ups are needed and the machine sleeps 300 s between them. Can a quick recheck fix it, and at what price?
- **Method:** new setting `flame_recheck_s` (default 30 s, 0 = off): in Normal, after a first positive flame read, the next wake-up is requested after `min(normal interval, flame_recheck_s)`. Python and C changed together; two new Python tests and one C test group (574 C checks, 24 Python tests); the parity streams (4 x 6000 random steps) compare the interval and still pass; runtime parity re-run. Delay and glint simulations with the real machine in `flame/python/notebooks/01_burst_vote_and_rules.ipynb`, sections 4 and 5.
- **Result:** delay of a flame appearing at a random moment, Eco: 300 / 450 / 600 s (min / mean / max) without recheck, **30 / 180 / 330 s with it**; Alert unchanged (30 / 45 / 60 s). Price: a steady light of 2 min opens a suspicion with probability 0.30 in Eco (0 before), one of 1 min with 0.10; certain from 5.5 min instead of 10 min. Extra wake-ups: about 3 per day at a glitch probability of 0.2 per read with the 5-of-8 vote.
- **Reading:** the delay still includes the wait for the next scheduled wake-up; only a hardware wake on the flame pin (not modelled, firmware dependent) removes it. The glint model is steady light; glitch and glint rates are not measured (no KY-026 recording). More sensitivity to short reflections means more camera wakes: energy per capture is unknown.
- **Decision:** kept on by default (30 s), to confirm with the team; switch off with `flame_recheck_s = 0`. **Status:** kept, open on the real module. **Evidence:** `python/tests/test_machine.py`, `c/test/test_state_machine.c`, the flame notebook.

## Not done yet
- Camera CNN block (supplies the `camera` input).
- Real flame sensor behaviour (KY-026 in sunlight).
- Eco cadence (300 s) and the window flush of RES-GAS-5 on a mode change.
- Fire on real data; neighbour boxes (gateway fusion).
- C/C++ port with shared vectors.
