# Fiche — Box firmware (ESP32-CAM)
**Runs on:** ESP32-CAM, deep sleep between wake-ups. **Spec:** §3-4 box. **Uses (in place):** `ai-data/box/{fwi,gas_chain,state_machine,flame,runtime,camera}`.
## Role
One wake-up = read sensors, run the chain, decide, talk on LoRa, sleep. Final application of everything built in `ai-data/box`.
## Input
BME680 (T, RH, gas bands), KY-026 flame via PCF8574, GPS NMEA, battery % and housing T (assumed I2C parts), supply-OK line, OV2640 (only on suspicion), downlink frames. Weather wind/rain are **simulated** (flagged SIM_WX), the gateway can override.
## Output
FFP frames (alert ×3 until acked, state, heartbeat 600 s, telem, pos, last gasp), next sleep time, retained RTC state (`box_retained_t`), NVS key-values.
## Design
- `core/` is portable C99 with a HAL struct (`box_hal.h`): same code on the ESP32 and in the host tests. `box_app_wake()` is one wake-up and returns seconds to sleep.
- `box_link`: send/ack/queue/dedupe/relay/downlink rules (see docs/PROTOCOL.md). Force-alert shortens sleep to 30 s, never lowers anything.
- Camera: 160×120 gray quality check, then JPEG POST to the gateway; the CNN runs on the gateway.
- `main/` + `components/` = ESP-IDF layer (HAL, drivers, Kconfig for box id, frequency, Wi-Fi, gateway URL).
## Metrics and pass criteria
| Check | Criterion | Result |
|---|---|---|
| Host tests with mock HAL | 0 failures | 969 checks pass |
| Scenarios `quiet/smoke/fire/fault` (box_sim) | fire → ALERT frames; fault → last gasp; quiet → heartbeats only | pass, used by the gateway end-to-end test |
## Limits
Wind and rain are simulated and flagged. Downlink commands are delivered in the ack of the next transmission.
## Build
Host: `make -C project/firmware/box/host test|sim`. Board: `idf.py set-target esp32 && idf.py menuconfig` (Box configuration) `&& idf.py build flash` in `project/firmware/box`.
