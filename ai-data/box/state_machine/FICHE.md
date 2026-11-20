# Fiche — Box state machine

**Runs on:** Box (ESP32-CAM). **Spec:** §5.2 figure 3, §3.2 (modes), §7.2 (levels), §8 (open decision 2: pump).
**Python reference:** `python/`. **C port for the ESP32:** `c/` (`state_machine.h`, one `sm_step` per wake-up; checked against the Python reference).

## Role
Decides alone, without the gateway: Normal → Suspicion → Fire. Sets the scan interval, wakes the camera, drives the local actuator, schedules the frames.

## Input (one tick)
| Field | Source |
|---|---|
| `gas_smoke`, `gas_fault`, `gas_score` | gas chain (`cls == smoke`, `cls == sensor_fault`) |
| `flame` | KY-026, one yes / no per wake-up from the burst vote (`../flame`) |
| `camera` | None, or `(label, confidence)` after a capture: `fire` / `smoke` / `background`. The label comes from the **gateway CNN**; the box only captures and sends (`../camera`). No answer (no Wi-Fi, gateway down, image refused) = `None`: the box decides alone |
| `fwi_mode`, `fwi_danger` | FWI engine (`eco` / `alert`, class 0 to 5) |
| `battery_low`, `housing_hot`, `supply_fault` | supervision |
| `dt_s` | time since the previous tick |

## Output
State, scan interval, `camera_on`, `gps_on`, `actuator`, reason codes (gas, flame, camera, fwi), list of frames to send (kind and repeat count), `last_gasp`.

## Rules (spec text → rule)
| Spec | Rule |
|---|---|
| Normal: heartbeat, low duty, camera and GPS off | interval 300 s (Eco), 30 s (Alert FWI), 3600 s (Survival, heartbeat only) |
| Normal → Suspicion on gas or flame | gas class smoke, or flame seen on 2 reads in a row (KY-026 sunlight reflections) |
| First flame read in Normal | wake again after `flame_recheck_s` = 30 s (never longer than the normal interval; 0 = off): confirms or drops the read quickly, also in Survival |
| Suspicion: scan every 30 s, camera woken | one capture per 30 s at most, camera off after each result |
| Suspicion → Fire on confirmed | camera `fire` or `smoke` above the confidence threshold, **or** gas smoke **and** flame together |
| Suspicion → Normal on clears | no trigger for 10 scans (5 min) |
| Fire: alert to gateway, local actuator | alert frame sent 3 times, priority; pump on; latched until reset or 30 min all clear |
| Last-gasp frame on temperature or supply fault | one frame, once |
| Pump pre-wetting (open decision 2) | high FWI and Suspicion → pre-wet; Fire → pump on |

## Metrics and pass criteria (set before running)
| Metric | Criterion |
|---|---|
| Transition tests | every rule above has a test |
| Camera wakes on clean air (real gas data, replay) | reported per hour and per day; no threshold (energy is measured on the board) |
| Time from burn start to Suspicion (real gas data) | reported; Suspicion must be reached in every episode |
| Fire without camera and without flame | impossible (test) |

## Known limits
- Camera result is injected: the vision classifier is a separate block (`gateway/vision`).
- Thresholds (2 flame reads, 10 clear scans, 30 min Fire hold, 30 s flame recheck) are provisional assumptions.
- Survival mode behaviour (flame as a hardware wake source) is an assumption of this fiche.

## C port (ESP32)
- `sm_machine_t` is plain data (no pointers): the runtime copies the fields that matter (state, clear count, Fire hold timer, last-gasp flag) to flash on every change, so a Fire latch survives a reset (`../runtime`).
- The camera label is an enum (`SM_CAM_BACKGROUND`, `SM_CAM_FIRE`, `SM_CAM_SMOKE`); any other value never confirms.
- Frames are a fixed array of at most `SM_MAX_FRAMES` (4) entries `(kind, repeats)`; the worst case in the Python rules is two.
- Tests: `make test` in `c/` (574 checks: the Python cases plus flame recheck and bad arguments); parity: `python/tests/test_c_parity.py`, 4 random streams of 6000 steps (all inputs, resets, dt from 10 s to 3600 s), every state visited, outputs identical.
