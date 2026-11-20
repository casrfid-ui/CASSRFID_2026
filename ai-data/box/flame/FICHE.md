# Fiche — Box flame sensor processing

**Runs on:** Box (ESP32-CAM, KY-026 flame module). **Spec:** §5.2 (flame input of the state machine), §3.2 (Survival: flame as hardware wake source).
**Python reference:** `python/`. **C port for the ESP32:** `c/` (checked against the Python reference).

## Role
Turn a short burst of digital reads of the flame module into **one yes / no per wake-up**, robust to single-sample glitches. The state machine then applies its own rule (2 yes in a row, see `../state_machine`).

## Input (one wake-up)
| Field | Unit | Note |
|---|---|---|
| `raw[n]` | 0 / 1 | digital output (DO) of the KY-026, `n` reads taken by the firmware at a fixed spacing (default 8 reads, 10 ms apart: the spacing is a firmware choice, not used by the processing) |

The analog output (AO) is **not used**: no recording of it exists to set a threshold on.

## Output
| Field | Meaning |
|---|---|
| `detected` | majority vote of the burst: `positives >= vote_ratio * n` |
| `ratio` | fraction of positive reads, 0..1 |
| `transitions` | number of 0↔1 changes in the burst (flicker count) |
| `n` | reads in the burst |

## Stages
| # | Stage | Rule |
|---|---|---|
| 1 | polarity | `active_low` (default true: the module pulls DO low on flame, **to check on the module**): a read is positive when `raw == 0`; otherwise when `raw != 0` |
| 2 | vote | burst is positive when positives ≥ `vote_ratio` × n (default 0.625 = 5 of 8) |
| 3 | flicker (optional) | counts transitions; the rule `transitions >= flicker_min` is **off by default** (`flicker_min = 0`) because no real flame recording supports it |

## Metrics and pass criteria (set before running)
| Metric | Criterion |
|---|---|
| Unit tests | polarity, vote limits, flicker count, bad input |
| C = Python | identical outputs on random bursts (all lengths 1..32, both polarities) |
| False yes per day from single-read glitches | computed analytically and by simulation as a function of the glitch rate; reported, no threshold (no measured glitch rate) |
| Detection delay of a steady flame | reported per mode (state machine's 2-read rule plus 30 s recheck): 30 / 180 / 330 s min / mean / max in Eco, 30 / 45 / 60 s in Alert, measured with the real machine; 300 / 450 / 600 s in Eco without the recheck |

## Known limits
- The notebook studies the *rules* (vote, two-read rule, recheck) on modelled glitch, sunlight and flicker signals; the vote ratio and burst length are tuned on KY-026 bench recordings.
- Sunlight steadily lighting the module gives all-positive bursts: the vote cannot reject it. Only the 2-read rule and the second witness (gas, camera) protect against it.
- Polarity, vote ratio and burst length are assumptions to confirm on the module (potentiometer threshold, range, field of view are unmeasured).
- The 2-read rule counts *wake-ups*: a real flame is reported after 0.5 to 5.5 min in Eco (mean 3 min) and 30 to 60 s in Alert, thanks to the 30 s recheck of the state machine (`flame_recheck_s`); without it, 5 to 10 min in Eco. The price is a higher sensitivity to short reflections (RES-FL-1, RES-SM-4). The first part of the delay, the wait for the next scheduled wake-up, needs a hardware wake on the flame pin (not modelled).

## Where it plugs in
`../runtime`: when a wake-up carries a burst (`flame_n > 0`), the runtime processes it and passes `detected` to the state machine as the flame read; otherwise it uses the plain flag. A refused burst (length outside 1..32) falls back to the flag and is reported (`flame_status = -1`).
