# Box flame sensor

Code: `ai-data/box/flame/` (`python/` reference, `c/` ESP32). Fiche: `ai-data/box/flame/FICHE.md`. Notebook: `ai-data/box/flame/python/notebooks/01_burst_vote_and_rules.ipynb`.

## RES-FL-1 · What do the vote and the 2-read rule do, and does the C port equal the Python? (12 Nov)
- **Question:** the flame input is a burst of digital reads. What does the majority vote buy against glitches, what delay does the state machine's 2-wake-up rule impose on a real flame, and can a steady light be rejected?
- **Method:** (a) unit tests (Python 13 incl. C parity, C 43 checks) and parity on 5000 random bursts (lengths 0 to 33, both polarities, several vote ratios and flicker limits); (b) runtime hook: 400 C checks, runtime parity re-run with random bursts on 20 % of the wake-ups; (c) notebook on **simulated** bursts: binomial formula checked against `process` (300 000 bursts per point), false suspicions per day from the real state machine with flame input alone (300 days Eco, 30 days Alert), delay of a flame appearing at a random phase (4000 trials per mode), steady glints of various durations (3000 trials), and an optional flicker rule on an assumed flame model.
- **Result:**
  - Formula and code agree within 1.7 standard errors at five values of the glitch probability $p$.
  - At $p=0.1$ per read, a single read is positive 10 % of the time, the 5-of-8 vote 0.043 %. False suspicions: none for $p\le 0.1$ with the vote (300 days Eco, 30 days Alert); a single read gives 0.1 to 2.9 per day in Eco (formula). At $p=0.2$: 5 events, 0.017 per day Eco.
  - **Delay of a real flame without recheck: 300 / 450 / 600 s (min / mean / max) in Eco, 30 / 45 / 60 s in Alert**, simulated with the real machine; equals $T$, $1.5T$, $2T$. With the 30 s recheck added afterwards (RES-SM-4): 30 / 180 / 330 s in Eco.
  - Steady light: passes the vote (8 of 8, no transition). In Eco a glint shorter than 5 min never opens a suspicion; in Alert any glint longer than 30 s can.
  - Flicker rule on the assumed flame model: $\tau_{\min}=1$ cuts detections from 0.81 to 0.29, $\tau_{\min}=2$ to 0.13.
- **Reading:** **no KY-026 recording exists.** Glitch rate, flicker and sunlight are models with assumed parameters: the results are the arithmetic of the rules, not a measure of the module. Independent glitches are assumed; real ones are probably correlated, so the vote is probably less effective than shown. In the first test run, two Python test expectations were wrong (4 transitions, not 3, in `[0,1,0,1,0,0,0,0]`; a flame detection rate of 0.808 sits on my `> 0.8` bound), none in the code.
- **Decision:** vote 5 of 8, active low, flicker rule off: kept as defaults, to confirm on the module. The 5 to 10 min flame delay in Eco was recorded as a design weakness and then reduced by the recheck of RES-SM-4. **Status:** open.
- **Evidence:** notebook, `python/tests/`, `c/test/`, `ai-data/box/runtime/python/tests/test_c_parity.py`.

## Not done yet
- Record the real module (dark, sunlight, reflections, a lit flame at known distances): polarity, glitch rate, flicker, range.
- Second remedy for the Eco delay, not tried: a second burst a few seconds after the first inside the same wake-up. Hardware wake on the flame pin: not modelled.
- Burst length and spacing the firmware can afford; energy of a burst.
- Analogue output (AO): not used, no data to set a threshold.
