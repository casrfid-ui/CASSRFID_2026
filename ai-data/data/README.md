# data

`Dataset Smoke Detection/` (not versioned): Matteo Anedda, University of Cagliari, Mendeley Data,
DOI 10.17632/48j7mm8k56.1, CC BY 4.0. Real BME688/690 smoke recordings, 20 CSV files (5 nodes × 4 heater profiles).
Download from https://data.mendeley.com/datasets/48j7mm8k56 and extract here, or set `CAS_MENDELEY_DIR`.

`fire detection/` (not versioned): D-Fire in YOLO format, 2 classes (`smoke`=0, `fire`=1), 21 527 images (train 14 122, val 3 099, test 4 306).
Inventory and limits: `docs/research/box-camera.md` (RES-CAM-2). Leak-free split by near-duplicate groups: `vision_split/split_v2.csv` (RES-CAM-3), built with `../tools/dedup_groups.py`.
