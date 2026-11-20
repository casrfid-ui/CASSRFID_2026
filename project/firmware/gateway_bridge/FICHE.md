# Fiche — Gateway bridge firmware (ESP32)
**Runs on:** gateway ESP32 with RA-02, SIM800L, switch for the SBC supply. **Spec:** §3 gateway.
## Role
Always-on radio and SMS front end so the SBC can sleep, and a safety net if the SBC is down.
## Input / output
LoRa frames from the boxes → acks + forwarding to the SBC over UART; commands/time from the SBC → boxes; SMS requests from the SBC → SIM800L.
## Design
- Ack within ~120 ms for each ACK_REQ frame; then up to 2 queued commands (max 2 deliveries each) and the time.
- Dedupes before forwarding; buffers 32 frames while the SBC is off; powers the SBC on for a priority frame, 8+ waiting frames, or periodically; power-cycles it once if it never says HELLO; cuts power after BYE.
- **Emergency SMS:** FIRE alert or LAST_GASP not taken over (`DISPATCHED`) within 60 s → the ESP32 sends the SMS itself to the configured numbers; max one per 15 min per box.
- UART: HDLC-like framing, CRC-16 ([docs/PROTOCOL.md](../../docs/PROTOCOL.md)).
## Metrics and pass criteria
| Check | Criterion | Result |
|---|---|---|
| Host tests (mock radio, UART, modem script) | 0 failures | 49 checks pass |
| HDLC C = Python | identical bytes | pass (gateway integration test) |
## Limits
SIM800L is 2G: check operator coverage and the SIM. SBC power switch circuit is not designed yet.
## Build
Host: `make -C project/firmware/gateway_bridge/host test`. Board: `idf.py build flash` in `project/firmware/gateway_bridge`.
