# FICHE — Operator dashboard (platform/)

## Role
The only human-facing part of the network. It shows the state of every box and of the gateway, raises the alert, lets the
operator acknowledge it and follow every automatic action. It never decides an alert: decisions stay on the boxes and on
the gateway fast path. If the dashboard is down, boxes, gateway, SMS and the drone mission keep working.

## Inputs
| From | How | Content |
|---|---|---|
| Gateway dispatcher (push) | `POST /api/alerts`, `/api/missions`, `/api/email` (bearer `ingest_token` = gateway `dashboard_token`) | alert payload, drone mission JSON, email request |
| Gateway uplink (push, NAT friendly) | `POST /api/gateway/snapshot` | `/v1/status` snapshot + recent timeline; the response carries queued operator commands |
| Gateway HTTP API (pull, LAN) | `GET /v1/status`, `/v1/timeline`, `/v1/risk`, `/v1/models` every `poll_s` | same data when the dashboard can reach the gateway |
| Operator (browser) | REST + Server-Sent Events | acknowledge, commands, tests |

## Outputs
- Web UI: live site map, alert banner and panel (L1 to L5), action timeline, per-box health, charts (gas score, FWI components,
  battery, signal), fire-weather forecast, drone mission, system health.
- Operator commands to the gateway: `ack`, `ping`, `force_alert`, `reset_fire`, `thresholds`, `sim_weather`, `test_sms`.
- Emails (SMTP when configured, otherwise recorded as `logged`).

## Data
SQLite (`dashboard.db`): alerts, missions, emails, gateway events (mirror), per-box time series, command queue, key-value
(latest snapshot, risk, models). Everything shown can be rebuilt after a restart.

## Pass criteria
1. A gateway alert POST appears in the UI in under 1 s (SSE), with level, box, reasons and coordinates.
2. An operator acknowledgement reaches the gateway (direct call in pull mode, or in the next snapshot response in push mode).
3. Losing the gateway link is visible within `2 x poll_s` (status "gateway offline"), never silent.
4. Ingest endpoints refuse a wrong token (401); the UI works read-only without an operator token when none is configured.
5. End-to-end test: the real `ffn_gateway.Gateway`, fed with the C box simulator frames, drives the dashboard from Normal to
   L3 fire, then the operator acknowledgement clears it.
6. UI usable at 1366 x 768 (projector) and on a phone; colour is never the only carrier of meaning; keyboard reachable.

## Not in scope
User accounts and roles (one operator token), map tiles (the site map is drawn from GPS positions, so it works offline).
