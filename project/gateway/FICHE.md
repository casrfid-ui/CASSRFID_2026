# Fiche — Gateway application (SBC)
**Runs on:** Khadas VIM4 / Raspberry Pi 4, Python ≥ 3.10, numpy. **Spec:** §5-6 gateway, alerts, dashboard, drone. **Uses (in place):** `ai-data/gateway/{risk_gru,fwi_forecast,spread_source,gas_trend}`.
## Role
Turn frames into decisions and actions: fusion across boxes, alert levels with reasons, dispatch to dashboard/SMS/email/drone, predictions for the dashboard.
## Input
Messages from the bridge (UART), camera events from the vision service (`POST /v1/camera-event`), operator ack (`POST /v1/ack`), config JSON.
## Output
SQLite (frames, timeline events, outbox), HTTP API `/v1/*`, SMS requests and commands to the bridge, dashboard webhooks, drone mission JSON (simulated).
## Design
| Module | Job |
|---|---|
| `uart_link` | HDLC mirror, typed messages, serial/in-memory transport |
| `registry`, `store` | latest state per box; persistence |
| `fusion` | log-odds fusion: per-witness LLR of the latest reading, decay 15 min, prior from FWI danger class, SPRT thresholds from α, β |
| `alerts` | L1..L5, latch, lost-box timer, maintenance rules |
| `dispatch`, `drone`, `downlink` | outbox with retry, one SMS per number per episode (skipped if the bridge already sent), mission, commands |
| `models`, `slowpath` | registry of `ai-data` models with phase B slots; periodic predictions in an isolated step each |
| `api`, `app` | stdlib HTTP server; wiring and run loop |
**Rules:** fast path never waits for the slow path; box FIRE is never overruled; flame absence is not evidence; warm-up and faulty scans give no gas evidence; a low-confidence vision positive is ignored.
## Metrics and pass criteria
| Check | Criterion | Result |
|---|---|---|
| Unit + API + slow path + dashboard uplink | pass | 30 tests pass |
| End to end with real C box frames (fire, quiet, fault) | fire → one L3 episode, 1 drone mission, 1 SMS per number; quiet → no SMS; fault → L4/L5, never L3 | 4 tests pass |
| Fusion sensitivity | same evidence confirms at danger 5, not at danger 1 | pass (default rates) |
## Limits
Fusion rates and priors are default values, calibrated later on controlled field recordings. Wind direction is simulated and flagged. Slow-path models are demo models trained on synthetic and recorded data.
## Run
`pip install -e project/gateway[serial]` · `python -m ffn_gateway --config config/gateway.json` · tests: `cd project/gateway && python3 -m pytest -q`
