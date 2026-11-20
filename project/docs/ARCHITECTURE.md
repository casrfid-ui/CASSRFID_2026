# Architecture

```
 box 1 (ESP32-CAM) ──LoRa 433 MHz, 16-byte FFP frames──┐
 box 2 (ESP32-CAM) ──LoRa (also relays the other box)──┤        ┌────────── Wi-Fi: JPEG ──► SBC vision service
                                                       ▼        │                           POST /v1/frame
                                   gateway bridge (ESP32 + RA-02 + SIM800L)                      │ label
                                   · acks every ACK_REQ frame (~120 ms)                          ▼
                                   · queues commands/time for the boxes            gateway app (SBC, Python)
                                   · powers the SBC on demand                      POST /v1/camera-event
                                   · emergency SMS if the SBC does not take over
                                                       │ UART 115200, HDLC + CRC-16
                                                       ▼
                                   gateway app: ingest → registry → fusion → alerts → dispatch
                                                                  │           │         ├ dashboard webhook (outbox, retry)
                                                  slow path ◄─────┘           │         ├ SMS (via bridge) / email
                                  (5 models, minutes)                         │         └ drone mission (simulated)
                                                                              └ downlink: thresholds, force-alert, reset ──► bridge ──► boxes
```

## Decision split
- **Box decides alone** (state machine, gas chain, flame, camera quality + vision call). Loses nothing if every link is down.
- **Bridge never depends on the SBC for the worst case**: an ALERT in FIRE or a LAST_GASP not taken over by the SBC within 60 s is sent by SMS from the ESP32.
- **Fast path (gateway, seconds)**: Bayesian + SPRT fusion with the FWI as prior; alert levels; dispatch. Never waits for the slow path.
- **Slow path (gateway, minutes)**: ignition-risk GRU, FWI forecast 1-3 d, spread isochrones, source localisation, gas trend. Informational: **no model can raise or lower an alert**.
- **Hard rule**: the box's own FIRE is L3 and is never overruled by fusion; fusion only adds.

## Where each `ai-data` block runs
| Block | Where | How it is reused |
|---|---|---|
| fwi, gas_chain, state_machine, flame, runtime, camera (C) | box | compiled in place by `firmware/box/components/ai_box_blocks` |
| risk_gru, fwi_forecast, spread_source, gas_trend | SBC | added to `sys.path` by `gateway/src/ffn_gateway/models.py` |
| vision (CNN/YOLO) | SBC service | HTTP service, ONNX or YOLO weights set in its config |

## Alert levels
L1 FWI high · L2 suspicion · L3 fire (latched until operator ack and no box in FIRE) · L4 box lost / last gasp · L5 maintenance. Severity order: L3 > L4 > L2 > L5 > L1.

## Timing (from the box host simulator, to be re-measured on hardware)
Eco scan 300 s · Alert scan 30 s · heartbeat 600 s · Suspicion/Fire: box listens 20 s between scans · alert sent up to 3×, stops on ack.
**Known limit:** commands reach a box only when it transmits (heartbeat 600 s, or while in Suspicion/Fire).
