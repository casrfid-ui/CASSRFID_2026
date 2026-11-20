# FFP — the 16-byte LoRa frame (and the UART)

Reference code: C `protocol/c`, Python `protocol/python/ffp`; `test_c_parity.py` checks both on the same vectors.

| Byte | Content |
|---|---|
| 0 | type (4 b) · flags (4 b): SIM_WX 1, RELAYED 2, ACK_REQ 4, PRIORITY 8 |
| 1 | origin (4 b) · destination (4 b). Boxes 1..7, gateways 8..11, dest 0 = any gateway, 15 = broadcast |
| 2 | sequence number |
| 3..14 | payload (12 bytes) |
| 15 | CRC-8, poly 0x07, init 0 (check value of "123456789" = 0xF4) |

Types: 1 ALERT · 2 STATE · 3 HEARTBEAT · 4 LAST_GASP · 5 TELEM · 6 POS · 8 ACK · 9 CMD · 10 TIME.

## STATUS payload (types 1-4)
| Byte | Bits |
|---|---|
| p0 | state 2 · mode 2 (eco/alert/survival) · reasons 4 (gas, flame, camera, fwi) |
| p1 | gas score u8 |
| p2 | gas class 2 · faults 3 · warmup 1 · flame 1 · scan_bad 1 |
| p3 | camera label 2 · valid 1 · status 4 |
| p4 | camera confidence u8 |
| p5 | flags: battery_low, housing_hot, supply_fault, clock_unsynced, storage_error, gps_on, pump, camera_on |
| p6 | FWI × 2 |
| p7 | danger 3 · fwi_updated 1 · provisional 1 · repeat 2 |
| p8 | battery % |
| p9..11 | gas band depths × 64 |

TELEM: temp×100 i16, RH×2, wind km/h, rain×10, FFMC×2.5, DMC, DC u16, ISI×5, BUI, history hours + provisional. POS: lat/lon e7 i32, alt i16, sats, fix.
ACK: acked seq/type, flags (OPERATOR 1, SBC_UP 2, FROM_BRIDGE 4), rssi, snr×4, gateway id, alert level.
CMD: id + 6 args — SET_THRESH (smoke_on, smoke_off, camera conf, ×100), RISK_PRIOR, FORCE_MODE (raise only), RESET_FIRE, SIM_WX, SET_SF, PING. TIME: unix u32 + UTC offset in quarter hours.

## Box rules
Alert repeated up to 3× with spacing, stop on ack · routine queue of 16, oldest heartbeat/telem dropped on overflow · duplicates dropped · other box's frames relayed once (RELAYED) when no gateway ack is heard · thresholds clamped on the box (smoke_on 0.25-0.80, smoke_off 0.10-0.60, camera 0.40-0.90) · TIME accepted only if > 1.7e9.

## Bridge ↔ SBC UART
`0x7E | type | payload | CRC-16/CCITT-FALSE (BE) | 0x7E`, escape `0x7D` (byte ^ 0x20); check value 0x29B1.
Bridge→SBC: 0x01 RX_FRAME [rssi i8][snr i8][16 B] · 0x02 STATUS (13 B) · 0x03 SMS_RESULT [id lo hi][status] · 0x04 EMERGENCY [box][type][n numbers].
SBC→bridge: 0x80 HELLO · 0x81 TX_FRAME [bit0 = send now][16 B] · 0x82 SEND_SMS [id lo hi][nl][number][text] · 0x83 DISPATCHED [box] · 0x84 BYE · 0x85 SET_NUMBERS (';' separated) · 0x86 SET_LEVEL · 0x87 SET_TIME [u32 BE][offset q] · 0x88 PING.

## Camera upload (Wi-Fi, box → SBC vision service)
`POST /v1/frame` with `X-Box-Id`, `X-Req-Id`, `X-Time`, `X-Reasons`; answer `{"v":1,"id":N,"label":"fire|smoke|background","conf":c,"ms":m}`.
The vision service then calls the gateway `POST /v1/camera-event {"box","label","conf","ms"}`.

## Gateway HTTP API (for `platform/`)
GET `/health` · `/v1/status` · `/v1/boxes` · `/v1/alerts` · `/v1/timeline?limit&kind` · `/v1/risk` · `/v1/models`
POST `/v1/ack` · `/v1/camera-event` · `/v1/cmd {box,cmd}` · `/v1/sim/weather {box,wind_kmh,rain_mm}` · `/v1/test/sms`
Bearer token if `api_token` is set. The dashboard webhook format (`/api/alerts`, `/api/missions`, `/api/email`) is defined here and implemented by `platform/server`.
