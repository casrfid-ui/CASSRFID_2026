# Fiche — Box camera (capture and send)

**Runs on:** Box (ESP32-CAM, OV2640). **Spec:** §5.2 figure 3 (camera on suspicion only), §3.3 (dark or blocked image = sensor fault), §5.4 (camera frames never travel over LoRa; full frames reach the gateway over Wi-Fi in the demo).
**C port for the ESP32:** `c/` (host-tested with a mock of the hardware). **Python reference of the image-quality stage:** `python/`. **Gateway side (the CNN):** `../../gateway/vision`.

## Role (design decision of the team, 12 Nov: the CNN runs on the gateway, not on the box)
After an alert (state machine: `camera_on`), the box powers the camera, checks that the image is usable, sends **one JPEG to the gateway over Wi-Fi** and receives `fire | smoke | background` with a confidence. The result goes back to the state machine as the `camera` input of the next wake-up. The camera and Wi-Fi are powered only for this session and are always powered off at the end, on every path.

Without Wi-Fi, without gateway or on any failure the box **keeps deciding alone** (gas + flame): the camera is a confirmation, never a dependency. The failure is reported (status code) so the dashboard can show it.

## Session (one call, bounded in time)
| # | Step | Rule |
|---|---|---|
| 1 | power on camera | rail switched through a transistor |
| 2 | warm-up | grab and discard `warmup_frames` (default 3): auto-exposure settles |
| 3 | quality check | small grayscale frame (firmware gives it, ≤ 160 × 120): refuses a dark, blocked (uniform), saturated or blurry image |
| 4 | capture | one JPEG |
| 5 | Wi-Fi | connect (`wifi_timeout_ms`) |
| 6 | send | HTTP POST of the JPEG, up to `max_attempts` (default 2), `post_timeout_ms` each, all inside `session_budget_ms` (default 25 s) |
| 7 | parse | strict: version, request id, label, confidence in [0, 1] |
| 8 | power off | camera and Wi-Fi, always |

## Image quality (stage 3), on the grayscale frame
| Quantity | Definition | Flag when |
|---|---|---|
| mean | mean grey level (0..255) | `< 15` → DARK |
| std | standard deviation of the grey level | `< 4` → BLOCKED (uniform: lens covered, fogged, or fully dark/white) |
| saturated share | share of pixels ≥ 250 | `> 0.5` → SATURATED |
| gradient | mean absolute difference between neighbouring pixels (horizontal and vertical) | `< 1` and std ≥ 4 → BLURRY |

Any flag: no upload (`upload_even_if_poor` = false), status `CAM_E_QUALITY` with the flags. **All four thresholds are assumptions: no real OV2640 image exists in the project.**

## Protocol with the gateway (v1)
Request: `POST /v1/frame`, body = JPEG, headers `X-Box-Id`, `X-Req-Id` (u32, increases), `X-Time` (unix s), `X-Reasons` (state machine reason bits), `Content-Type: image/jpeg`.
Response 200: `{"v":1,"id":<req id>,"label":"fire|smoke|background","conf":0.934,"ms":210}`. Errors: non-200, with `{"v":1,"id":..,"error":"..."}`. The box rejects a response whose `id` differs from the request.

## Output (`cam_result_t`)
`status` (OK, power, capture, quality, Wi-Fi, timeout, HTTP, response), `valid` + `label` + `conf` (only when OK), quality numbers and flags, attempts, elapsed ms, HTTP status, model time reported by the gateway.

## Metrics and pass criteria (set before running)
| Metric | Criterion |
|---|---|
| Camera and Wi-Fi powered off on every path (success, quality refusal, Wi-Fi failure, timeout, bad response, capture failure) | every path, tested with a mock |
| Session never exceeds `session_budget_ms` (plus one operation) | tested with a mock clock |
| Quality check C = Python | identical outputs on random frames |
| Response parser accepts what the gateway sends and refuses malformed, stale, unknown-label and out-of-range answers | unit tests and an end-to-end test against the real gateway service |

## Known limits
- Nothing here ran on a board: the hardware hooks (`cam_hw_t`) are implemented only as a mock. Camera driver, Wi-Fi and HTTP code belong to the firmware.
- Thresholds of the quality check are assumptions. Energy and duration of a session (camera warm-up, Wi-Fi association, upload of a JPEG) are unknown; the default budget of 25 s must fit inside the 30 s Suspicion period.
- The result is used at the **next** wake-up (the session runs after the decision of the current one).
- A Wi-Fi link in a forest is the prototype's choice for the demo; in the field the spec only allows the detection result and a small crop over LoRa (§5.4).
