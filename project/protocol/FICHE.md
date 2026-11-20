# Fiche — Protocol (FFP, 16-byte LoRa frame)
**Runs on:** box, bridge (C), SBC (Python). **Spec:** §3 LoRa 433 MHz link, small frames.
## Role
One compact, checksummed frame for everything the boxes and gateway exchange, so that an alert costs ~16 bytes of airtime.
## Input / output
Typed bodies (status, telem, pos, ack, cmd, time) ⇄ 16 bytes. Layout in [docs/PROTOCOL.md](../docs/PROTOCOL.md).
## Design
Fixed length, CRC-8, 4-bit ids (7 boxes, 4 gateways), flags for simulated weather / relayed / ack requested / priority. Physical values stored as scaled integers; the Python classes expose the real units.
## Metrics and pass criteria
| Check | Criterion | Result |
|---|---|---|
| C round trips, CRC check value, bad inputs | 0 failures | 188 checks pass |
| C vs Python on the same vectors | identical bytes | 3 tests pass |
## Limits
Frame layout designed here (not from the spec); no encryption or signing; no air-time measurement yet (needs hardware).
## Status
`make -C project/protocol/c test` · `PYTHONPATH=project/protocol/python pytest project/protocol/python/tests`
