# project — the deployable system

Code that runs on the boards, built on the verified blocks in `../ai-data` (reused in place, never copied).
Phase 1 due 20/11/2026, final 09/12/2026.

| Folder | Runs on | What | Fiche |
|---|---|---|---|
| [protocol/](protocol/) | box, bridge, SBC | 16-byte LoRa frame (FFP): C codec + Python mirror, parity-tested | [FICHE](protocol/FICHE.md) |
| [firmware/box/](firmware/box/) | ESP32-CAM | wake-up application: sensing, `ai-data` blocks, state machine, LoRa link, camera upload | [FICHE](firmware/box/FICHE.md) |
| [firmware/gateway_bridge/](firmware/gateway_bridge/) | gateway ESP32 | LoRa receiver, acks, SBC power control, SIM800L emergency SMS, UART to the SBC | [FICHE](firmware/gateway_bridge/FICHE.md) |
| [firmware/common/sx127x/](firmware/common/sx127x/) | both ESP32 | shared RA-02 driver | — |
| [gateway/](gateway/) | SBC (VIM4 / Pi 4) | Python app: ingest, fusion, alert levels, dispatch, drone (simulated), slow-path models, HTTP API | [FICHE](gateway/FICHE.md) |
| [docs/](docs/) | — | [ARCHITECTURE](docs/ARCHITECTURE.md) · [PROTOCOL](docs/PROTOCOL.md) | — |

The dashboard web app lives in `../platform/` and consumes the gateway HTTP API (`/v1/*`); it is not part of this folder.

## Run all the tests (no hardware, no ESP-IDF needed)
```
make -C project/protocol/c test                                  # 188 checks
PYTHONPATH=project/protocol/python python3 -m pytest project/protocol/python/tests -q
make -C project/firmware/box/host test                           # 969 checks
make -C project/firmware/box/host sim                            # builds box_sim (used by the gateway integration test)
make -C project/firmware/gateway_bridge/host test                # 49 checks
cd project/gateway && python3 -m pytest -q                       # 34 tests incl. end to end with the C box
python3 project/gateway/scripts/replay_box_sim.py                # readable timeline of a fire scenario
```
Wind and rain are simulated in the prototype and flagged in every frame (`SIM_WX`); the drone flight is simulated (MAVLink mission file).
