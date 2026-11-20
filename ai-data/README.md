# ai-data

AI lives where it runs.

| Folder | Runs on | Blocks |
|---|---|---|
| `box/gas_chain/` | Box (ESP32-CAM, BME680) | `python/` + `c/`: scan → quality → filter → T/RH compensation → baseline → depth bands → score + class. **Done (v1, real-data replay; C port equal to Python)** |
| `box/fwi/` | Box | FWI engine (`python/` reference + `c/` ESP32 port): daily codes checked against xclim (5e-7), hourly FFMC, danger class → mode. **Done (daily chain equal to xclim)** |
| `box/state_machine/` | Box | `python/` + `c/`: Normal → Suspicion → Fire, modes, camera wake, frames. **Done (C port equal to Python; camera and flame inputs injected)** |
| `box/flame/` | Box (KY-026) | `python/` + `c/`: burst of digital reads → majority vote → one yes / no per wake-up. **Done (vote checked by exact binomial formula and simulation)** |
| `box/runtime/` | Box | `c/` + `python/`: FWI hourly → gas chain → state machine in one call per wake-up, flash copies, ESP-IDF layer. **Done, host-tested** |
| `box/camera/` | Box (OV2640) | `c/` + `python/`: camera on only after the alert → image quality check → JPEG sent to the gateway over Wi-Fi → label back. **Done, host-tested with a camera mock** |
| `gateway/vision/` | Gateway | HTTP service: JPEG in, fire / smoke / background out (ONNX classifier or YOLO detector); `train/`: leak-free lists, OV2640 degradations, two-phase training, decision metrics for the team PC. **Service and training pipeline done** |
| `gateway/` | Gateway | slow-path blocks loaded in place by `project/gateway`: `risk_gru`, `fwi_forecast`, `spread_source`, `gas_trend`; shared tools in `common/` |
| `data/` | — | raw data sets (not versioned) |
| `tools/` | — | `run_notebook.py` (stores notebook outputs, no Jupyter needed); `dedup_groups.py` (near-duplicate groups and leak-free split of an image set) |

Research log: `../docs/research/`.
