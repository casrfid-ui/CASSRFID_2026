# Challenge requirements: where to find the evidence

Each requirement and scoring criterion of the "Edge AI & IoT for Resilient Smart Infrastructure" challenge, with the file, test or result that shows it.

## Challenge instructions

| # | Requirement | How this project meets it | Evidence |
|---|---|---|---|
| 1 | Identify a real-world problem | Forest fires in Tunisia and the Mediterranean: late detection under canopy, no grid or internet in the forest | `docs/report/` (problem section, sourced figures) |
| 2 | Sensing → Edge processing → Connectivity → Response | Box sensors (BME680 gas, KY-026 flame, OV2640 camera, GPS) → AI on the ESP32 → LoRa 433 MHz to the gateway → alerts L1 to L5, SMS, email, dashboard, drone mission | `project/docs/ARCHITECTURE.md`, `project/protocol/`, `project/gateway/` |
| 3 | Meaningful edge intelligence, not cloud-only | The box decides alone: FWI engine, 7-stage gas chain, flame vote, state machine (Normal → Suspicion → Fire). 60 raw values become one score and one class in a 16-byte frame. The gateway fuses boxes (Bayes + SPRT) with no cloud | `ai-data/box/*`, `project/gateway/src/ffn_gateway/fusion.py` |
| 4 | Appropriate technologies | ESP32-CAM, LoRa RA-02, ESP32 bridge with SIM800L, Khadas VIM4 / Raspberry Pi 4 gateway, C99 on the box, Python on the gateway, React dashboard | `README.md`, `project/README.md` |
| 5 | Functional prototype | Hybrid prototype: C firmware, gateway application and dashboard running end to end on real 16-byte frames | `platform/server/scripts/run_demo.py`, `project/gateway/tests/` |
| 6 | Demonstrate the complete system | Live demo: smoke on a box → suspicion → flame and camera confirm → fusion confirms fire → L3 alert, SMS, email, drone mission on the dashboard | `platform/README.md` (7-box scenario) |

Simulated in the prototype, and flagged as such: wind and rain values (`SIM_WX` flag in every frame) and the drone flight (MAVLink mission file).

## Phase 1 scoring criteria

| Criterion | Points | Evidence |
|---|---|---|
| Problem relevance and impact | 3 | Report: Tunisian and world fire figures, cost of late detection, expected impact (about 3 min from smoke onset to alert on recorded burns, 1 W solar per box) |
| Innovation, creativity and originality | 3 | Evidence fusion with explicit error rates (SPRT), weather-aware duty cycle from the Fire Weather Index, alerts that explain their reasons, bridge that sends SMS without the gateway computer; comparison with satellites, towers, camera and gas networks in the report |
| Quality of the proposed solution | 2 | One fiche per block before code (`FICHE.md`: inputs, outputs, data, metric, pass criterion); research log with every experiment, failures included (`docs/research/`, `ai-data/docs/research/`) |
| Technical implementation and Edge AI / IoT integration | 3 | See "Test results" below; C ports equal to the Python references; gateway end-to-end test driven by frames from the C box firmware |
| Functional prototype and video demonstration | 2 | Demo command in `README.md`; dashboard in `platform/` |
| CAS / CRFID integration and deployment potential | 1 | Embedded circuits and systems (ESP32, LoRa, low-power modes, solar); RFID / NFC box identity for commissioning, verification and maintenance, and the demo-to-field hardware path, both described in the report and pitch |

## Deliverables and rules

| Item | Status |
|---|---|
| Technical report, 4 pages maximum, anonymous | `docs/report/Forest_Fire_Network_Report.pdf`, 4 pages |
| 5-minute English pitch | prepared, about 4 min 50 s of speaker notes |
| Live demonstration | `platform/server/scripts/run_demo.py` |
| Anonymity | no team, member, university or branch name, logo or e-mail in the documents |

## Test results (no hardware needed)

| Part | Command | Result |
|---|---|---|
| LoRa frame protocol (C) | `make -C project/protocol/c test` | 188 checks, 0 failed |
| Box firmware (C) | `make -C project/firmware/box/host test` | 969 checks, 0 failed |
| Gateway bridge firmware (C) | `make -C project/firmware/gateway_bridge/host test` | 49 checks, 0 failed |
| Gateway application | `cd project/gateway && python3 -m pytest -q` | 34 passed |
| Dashboard backend | `cd platform/server && python3 -m pytest -q` | 13 passed |
| Box AI blocks, C ports | per block, see each `FICHE.md` | FWI 203, gas chain 2060, flame 43, state machine 574, camera 119, runtime 400 checks |

Key measured results:
- Gas chain on 38 episodes (13 097 scans) of two recorded burns: recall 1.000 in strong smoke, false smoke 0.0 % and 1.9 % on clean air, median delay about 3 minutes (`ai-data/box/gas_chain/python/notebooks/01_real_data_evaluation.ipynb`).
- FWI daily chain equal to xclim within 5e-7 (`ai-data/box/fwi/`).
- Flame burst vote: isolated glitches suppressed, checked by exact binomial formula and simulation (`ai-data/box/flame/python/notebooks/`).
