# Training the gateway detector (YOLO) on the team PC

Data: D-Fire in `ai-data/data/fire detection/`, split `ai-data/data/vision_split/split_v2.csv` (leak-free, RES-CAM-3).
Everything below runs on a PC with a GPU; none of the training was run in the workspace (no GPU, no PyTorch there).

```
pip install ultralytics opencv-python pyyaml          # AGPL-3.0: see the fiche
cd ai-data/gateway/vision/train

# 1. lists and data file for split_v2 (nothing is copied)
python make_lists.py "../../../data/fire detection" ../../../data/vision_split/split_v2.csv lists

# 2. OV2640-like copies of the train images (+ flare and night-like negatives on background images)
python build_degraded.py "../../../data/fire detection" ../../../data/vision_split/split_v2.csv deg --severity 0.6

# 3. smoke test of the whole chain (1 epoch, 1 % of the data), then the real run
python train.py --data lists/data_v2.yaml --extra-train deg/train_deg.txt --smoke --out runs_smoke
python train.py --data lists/data_v2.yaml --extra-train deg/train_deg.txt --model yolov8n.pt --out runs

# 4. image-level decision metrics on the held-out split
python predict_scores.py runs/fire_smoke_yolo.onnx "../../../data/fire detection" lists/test.txt scores.csv
python evaluate.py scores.csv --split-csv ../../../data/vision_split/split_v2.csv --recall 0.9 --frames-per-day 2880

# 5. serve it
python -m gateway_vision.server --model runs/fire_smoke_yolo.onnx --port 8080     # (YOLO adapter: see below)
```

## Why these choices
- **Split by near-duplicate groups**, not by image: the official D-Fire split leaks about half of val and test.
- **Two phases**: head first with the backbone frozen, then everything with a lower rate.
- **Light hue shift** (`hsv_h=0.01`): fire is orange.
- **Offline OV2640 degradations** (`degrade.py`): resolution loss, blur, white balance, vignetting, haze, dirt, noise, JPEG. Ranges are assumptions until calibrated on real OV2640 frames.
- **Night-like negatives**: in D-Fire 62 % of fire-only images are dark against 7 % of background images; a network can learn "dark = fire". `build_degraded.py` darkens background images, and `evaluate.py` reports a dark slice.
- **Burned-in label and date stamp** (27 % of the frames, more often on fire-only ones; the box frames have none): `build_degraded.py` masks it on part of the stamped images and pastes a synthetic one on part of the others, same probabilities for every class. After training, score the test list twice (`predict_scores.py` with and without `--mask-overlay`) and compare the overlay slice in `evaluate.py`.
- **Metrics that matter**: false alarms per day at a fixed recall, with confidence intervals from a bootstrap over groups; box mAP (`yolo val`) is secondary.

## Using the model in the gateway
`gateway_vision.yolo.YoloOnnxClassifier` loads the exported ONNX (class names come from its metadata), letterboxes to 640, decodes, applies NMS and returns fire / smoke / background to the box. Thresholds (default 0.25) must be set from the validation curve, not left at default.


## Notebook (recommande)

`notebooks/01_finetune_yolo.ipynb` enchaine tout : controle GPU, poids, controle des donnees, traitement d'images, fine-tuning en deux phases, metriques de decision (fausses alertes par jour a rappel fixe), seuils choisis sur la validation, calibration, export vers `../models/`, puis demarrage du service gateway et envoi de photos comme le fait une boite.

- Premier lancement : `PRESET = "smoke"` (quelques minutes), puis `"full"`.
- Windows : `pip install ultralytics` installe un PyTorch **CPU**. Installer d'abord `pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121` (cu118 / cu124 selon `nvidia-smi`), redemarrer le noyau.
- Variables d'environnement utiles : `CAS_REPO`, `FIRE_ROOT`, `SPLIT_CSV`, `OUT_DIR`, `MODEL_WEIGHTS`.
- Photos reelles OV2640 : les poser dans `ai-data/data/camera_photos/`, elles sont envoyees au service a la fin du notebook.
- Service seul : `python -m gateway_vision.server --model ../models/fire_smoke_yolo.onnx --thresholds ../models/thresholds.json --port 8080`.
- Client seul : `python -m gateway_vision.client http://IP:8080 --folder photos --annotate annotated --csv results.csv`.
