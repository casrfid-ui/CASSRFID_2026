# Forest Fire Prevention Network

IEEE CAS / CRFID challenge "Edge AI and IoT for Resilient Smart Infrastructure".

Solar sensor boxes watch the forest floor (gas, flame, camera, fire weather), talk to a gateway over LoRa, and the gateway fuses their evidence, raises graded alerts (dashboard, SMS, email) and sends a drone mission to the fire.

| Folder | Content |
|---|---|
| `ai-data/` | Edge AI blocks, organised by where they run: `box/` (ESP32-CAM: FWI, gas chain, flame vote, state machine, camera, runtime) and `gateway/` (vision service, FWI forecast, risk model, gas trend, spread and source); each with a `FICHE.md`, tests and notebooks |
| `project/` | The deployable system: 16-byte LoRa protocol, box and gateway-bridge firmware, gateway application (fusion, alert levels L1 to L5, dispatch, drone mission, HTTP API) |
| `platform/` | Operator dashboard: FastAPI backend linked to the gateway, React web app with live map, alerts, evidence and response timeline |
| `docs/` | Report, challenge requirements mapped to evidence (`CHALLENGE_COMPLIANCE.md`), research log (`docs/research/`, one entry per experiment) |

## Rules followed
- Every AI block has a fiche (`FICHE.md`) before code: inputs, outputs, data, metric, pass criterion.
- Every experiment is logged in `docs/research/` and `ai-data/docs/research/`, failures included.
- Splits by burn experiment, never at random inside a file.
- Wind and rain are simulated in the prototype and flagged in every frame (`SIM_WX`).

## Run the demo (gateway + dashboard, 7-box scripted scenario)
```bash
cd platform/server && pip install -r requirements.txt
python scripts/run_demo.py                          # then open http://127.0.0.1:3000
```

## Run the tests (no hardware needed)
```bash
make -C project/protocol/c test
make -C project/firmware/box/host test && make -C project/firmware/box/host sim
make -C project/firmware/gateway_bridge/host test
(cd project/gateway && python3 -m pytest -q)
(cd platform/server && python3 -m pytest -q)
(cd ai-data/box/gas_chain/python && python3 -m pytest -q)
```
