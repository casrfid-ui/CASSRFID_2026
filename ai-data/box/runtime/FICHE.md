# Fiche — Box runtime (FWI → gas chain → state machine)

**Runs on:** Box (ESP32-CAM). **Spec:** §5.2, §5.4. **Code:** `c/` (ESP32), `python/` (reference used by the parity tests).

## Role
One call per wake-up. It chains the three blocks and keeps the flash copies up to date. It reads no sensor and drives no output: the firmware does (`c/esp32/board.h`).

## Input (`box_tick_t`)
`unix_s` (RTC, UTC); weather (temperature, humidity, wind) when read; rain since the previous wake-up; one gas scan (10 × gas, T, RH) when performed; flame burst (digital reads of the KY-026, processed by `../flame`) or a plain flag; camera result (label from the gateway) when a capture and send session succeeded; battery low, housing hot, supply fault.

## Output (`box_output_t`)
State machine output (state, next interval, camera / GPS / pump, frames, last gasp, reasons), `want_gas_scan`, last FWI values, gas result, `storage_errors`, `clock_jump`.

## Rules
| Rule | Choice |
|---|---|
| FWI timing | one update per local hour (`unix_s + utc_offset_s`), at the first wake-up of the hour that has valid weather; the rain gathered since the previous update is the hour's rain |
| Invalid weather (NaN, out of range) | the hour is not applied and is retried at the next wake-up; the rain is kept; the last known mode and danger stay in force |
| First wake-up after a reboot | if the saved FWI hour is the current one, the hour is **not applied twice**; FWI values are recomputed from the saved codes and the current wind |
| Gas scan time step | seconds since the previous *used* scan (at least 1 s; 30 s for the first) |
| Flame | a burst replaces the plain flag; a refused burst falls back to the flag (`flame_status = -1`) |
| Survival (battery low) | the scan is ignored, `want_gas_scan` is false, `gas_smoke` is false |
| Gas class between scans | the last class stays in force (a flame wake-up between two scans still sees it) |
| State machine time step | seconds since the previous wake-up (0 for the first one and after a clock going backwards, flagged) |

## Flash copies (key-value store, keys ≤ 15 characters)
| Key | Content | Written |
|---|---|---|
| `fwi` | codes and 24 h rain history (228 bytes, CRC32) | every FWI hour |
| `rt_meta` | last FWI hour applied (20 bytes, CRC32) | every FWI hour |
| `gas_base` | gas baseline, 10 values (92 bytes, CRC32) | when first ready, then at most hourly, only in normal quiet air |
| `sm_state` | state, clear count, Fire hold timer, last-gasp flag (24 bytes, CRC32) | on state change and when the last-gasp frame is sent |

A damaged or absent copy falls back to the defaults. A Fire latch survives a reset until `box_runtime_reset_fire` or the 30 min all-clear.

## Pass criteria (set before running)
| Criterion | Result |
|---|---|
| C runtime = Python chain of the three blocks, tick by tick, on the real sample at 27 s and at the Eco pace, with random weather, rain, flame, camera, battery and supervision events | see RES-RT-1 |
| Reboot at any point keeps the state that must survive (Fire latch, baseline, FWI codes) and never applies an FWI hour twice | unit tests |
| A failed flash write never stops detection (reported in `storage_errors`) | unit test |

## Known limits
- ESP-IDF names a component after its folder; the four blocks all sit in a folder called `c`: in the firmware project they must be exposed under distinct names (see `c/CMakeLists.txt`).
- Wind and rain are simulated in the prototype; the FWI hour uses the weather of the wake-up that crosses the hour boundary, not an hourly mean.
- A reboot that lasts hours is not seen as a gap: the missing hours are simply absent from the rain history.
- Flash wear: about 2 writes per hour (FWI, meta) plus the baseline hourly: roughly 26 000 writes per year on three keys; NVS wear levelling covers this, to be confirmed on the chosen flash.
- No wake-up scheduling logic lives here: the firmware sleeps for `sm.interval_s` and also wakes on the flame pin.
- The frame payload (fields, LoRa format) is defined by the protocol (`project/protocol`).
- RAM: the whole runtime (`box_runtime_t`) is 2200 bytes on a 64-bit host (gas chain 1296, state machine 136, FWI 248); smaller on the 32-bit ESP32 apart from the doubles.
