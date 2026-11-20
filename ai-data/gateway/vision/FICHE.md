# Fiche — Gateway vision check (fire / smoke / background)

**Runs on:** gateway (Khadas VIM4 class). **Spec:** §5.4 (gateway vision re-check, optional, ONNX), §3.3, alert level L3 "camera confirms". **Box side:** `../../box/camera`.
**Decision of the team (12 Nov):** the performant CNN runs on the gateway; the box only takes and sends the photo.

## Role
Receives one JPEG from a box after an alert, classifies it into `background | fire | smoke` with a confidence and answers in the same HTTP response. Every frame and answer is stored for retraining and for the audit trail.

## Interface (protocol v1, same as the box fiche)
| | |
|---|---|
| Request | `POST /v1/frame`, body JPEG (≤ 2 MB), headers `X-Box-Id`, `X-Req-Id`, `X-Time`, `X-Reasons` |
| Answer 200 | `{"v":1,"id":N,"label":"fire","conf":0.934,"ms":210}` |
| Errors | 400 undecodable image or bad headers, 413 too large, 404 path, 500 model failure; body `{"v":1,"id":N,"error":"..."}` |
| Health | `GET /health` → `{"ok":true,"model":"<name>"}` |

### API for people, the dashboard and tests (the box never uses it)
| Endpoint | Role |
|---|---|
| `POST /v1/frame?debug=1` | same answer as the box protocol + detected `boxes` |
| `POST /v1/predict` | JPEG body, no headers, nothing stored: `{"alert":"fire\|smoke\|none","detected":bool,"label","conf","ms","image":{width,height},"detections":[{"class","score","box_px","box_norm"}],"model","thresholds"}` |
| `GET /v1/status` | model, thresholds, counters per verdict and errors, model latency (median, p95, max), last valid verdict per box, webhook counters |
| `GET /v1/events?limit=&label=&box=` | recent events, newest first (reloaded from `log.jsonl` after a restart) |
| `GET /v1/events/<file>.jpg[?annotated=1]` | stored photo, optionally with the boxes drawn |
| `--webhook URL` | every fire or smoke verdict received on `/v1/frame` is POSTed as `{"event": {...}}` (3 s timeout, failures counted, never blocks the box answer) |

Start: `python -m gateway_vision.server --model ../models/fire_smoke_yolo.onnx --thresholds ../models/thresholds.json --port 8080 --store received [--webhook http://dashboard/alert]`. No authentication and no TLS: local network only (open point).

## Two classifier back-ends (same service, same protocol)
- `OnnxClassifier`: 224×224 image classifier, 3 logits (below).
- `YoloOnnxClassifier` (`gateway_vision/yolo.py`): Ultralytics YOLO detector at 640 px; fire boxes are small (median 0.5 % of the image), so the detector is the intended model. Image-level rule: fire if best fire score ≥ thr, else smoke if best smoke score ≥ thr, else background (fire wins a tie). Detector scores are not calibrated probabilities. Training: `train/README.md`.

## Classifier contract
- ONNX file, input `[1,3,224,224]` float32, RGB, scaled to 0..1 then ImageNet mean/std; output `[1,3]` logits in the order **background, fire, smoke**; softmax on the gateway.
- Any model fitting this contract can be dropped in (`--model path.onnx`). Retraining is done on the team PC, offline.
- The confidence is a softmax score; a temperature calibration is fitted on a validation set before it is read as a probability.

## What exists now, and what does not
- Exists: protocol, preprocessing, ONNX runtime wrapper, HTTP service, frame/answer logging, tests (including against the real box C parser).
- **Does not exist: a trained network.** No dataset (D-Fire, Kaggle, Hugging Face are unreachable from the workspace) and no GPU/PyTorch. `models/plumbing_color_stub.onnx` is a **colour heuristic that only proves the plumbing**; it is not a detector and must never be shown as a result.
- Training recipe for the PC: `train/README.md` (detector) and `TRAINING.md` (older 224 classifier note).

## Metrics and pass criteria (set before running)
| Metric | Criterion |
|---|---|
| Protocol: answers accepted by the box C parser | all labels, e2e test |
| Error paths: bad JPEG, empty body, oversize body, missing headers, wrong path | correct status and JSON, service stays up |
| Latency of the service excluding the model | measured, reported |
