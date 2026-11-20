# Box camera and gateway vision

## RES-CAM-1 — Capture on the box, CNN on the gateway: protocol, session and service (12 Nov 2026)
**Question.** Can the box take a photo only after an alert, send it to the gateway and use the gateway's fire / smoke / background answer, while staying safe when anything fails?

**Method.**
- Box: C library `ai-data/box/camera/c` (quality check, request headers, strict response parser, session with hardware hooks), unit tests with a hardware mock; Python reference of quality and protocol with C/Python parity on random data.
- Gateway: `ai-data/gateway/vision/python` (preprocessing, ONNX wrapper, stdlib HTTP service, frame and answer log), tests over real HTTP; the answers are fed to the box C parser.
- Model: `models/plumbing_color_stub.onnx`, a colour heuristic built only to test the plumbing.

**Result.**
- Box C: 119 checks pass (quality flags, 13 protocol cases, 20+ session paths). Camera and Wi-Fi are off after every path tested: success, power failure, capture failure in warm-up, JPEG failure, 4 quality refusals, Wi-Fi failure, HTTP errors, stale id, garbage, gateway error, budget exhausted at several points.
- C and Python: quality numbers equal to 1e-9 on 60 random frames (flags identical); 13 gateway answers (valid, stale, wrong version, unknown label, confidence outside 0..1, error, truncated) get the same decision in both.
- Gateway: 6 tests pass (preprocess, contract, answer and log, 400/404/413 paths with the service staying up, 8 concurrent requests, answers accepted by the box C parser, stale id refused as -2, error body refused as -3).
- Service round trip on this host, 150 kB JPEG, 60 requests: median 6.5 ms, p95 8.3 ms, stub model 0 ms. The real network and the real CNN time are not measured.
- Firmware skeleton `runtime/c/esp32/main.c` now calls the session when the state machine asks for the camera, and passes only a valid label to the next wake-up; syntax-checked with stub headers only.

**Reading.**
- This proves the logic and the contract, nothing about detection. The stub separates three flat colours; it is not a detector.
- Quality thresholds (mean 15, std 4, saturated share 0.5, gradient 1) are assumptions, never tried on an OV2640 image.
- Camera warm-up, Wi-Fi association and JPEG upload durations and energy are unknown; the 25 s budget has to fit the 30 s Suspicion period and must be measured on the board.
- The label is used at the next wake-up, so confirmation arrives 30 s later in Suspicion.
- The spec forbids photos over LoRa: this design needs Wi-Fi between box and gateway, which the demo allows and the field would not.

**Decision.** Keep the architecture decided by the team (CNN on the gateway). The gateway CNN has to be trained on the team PC (`gateway/vision/TRAINING.md`) with D-Fire plus real OV2640 frames; calibrate the confidence before using the box confidence threshold.

**Status.** `kept` (plumbing), `open` (model, thresholds, board timings).
**Evidence.** `cd ai-data/box/camera/c && make test`; `cd ai-data/box/camera/python && python3 -m pytest`; `cd ai-data/gateway/vision/python && python3 -m pytest`.

## RES-CAM-2 — Inventory of the D-Fire data added to the repo (12 Nov 2026)
**Question.** What is in `ai-data/data/fire detection/`, and is it fit for the gateway CNN?

**Method.** Read all 21 527 label files; image sizes and a perceptual hash (dHash 8×8, Hamming ≤ 4) on a random sample (2 500 train, 800 val, 800 test, seed 0).

**Result.**
| Split | Images | Background | Fire only | Smoke only | Smoke + fire | Boxes smoke / fire |
|---|---|---|---|---|---|---|
| train | 14 122 | 6 458 | 770 | 3 836 | 3 058 | 7 794 / 9 638 |
| val | 3 099 | 1 375 | 174 | 845 | 705 | 1 756 / 2 176 |
| test | 4 306 | 2 005 | 220 | 1 186 | 895 | 2 315 / 2 878 |
- Classes: 0 = smoke, 1 = fire. No missing labels. Backgrounds (empty label files) are 46 % of the images.
- Fire boxes are small: median area 0.5 % of the image, 64 % under 1 %, 33 % under 0.25 %. Smoke boxes are large (median 14 %).
- Resolutions: 1280×720 (62 %), 640×360 (27 %), others (480×360, 640×352, 1920×1080, …). The OV2640 delivers up to 1600×1200 but the box will send a smaller JPEG: resolution to fix.
- **Leakage:** 290 of 800 val images (36 %) and 280 of 800 test images (35 %) have a near-duplicate in only 2 500 of the 14 122 train images (18 %). The full train set would give a higher share.

**Reading.**
- Probable near-duplicate frames of the same video across splits: val and test scores on the official split are **optimistic**. dHash at this threshold can also match flat scenes (sky, haze), so the exact share is not established; a stronger check (embeddings, whole set) is needed.
- Tiny fire boxes mean the 224×224 resize used by the gateway classifier loses most flames; a detector at 640 px (YOLO) or tiling is better suited. Fire-only images are rare (5 % of train).
- "Background" in D-Fire is not hard negatives (sunsets, red roofs, lights): to be added. No sequence or site id exists in the file names, so a split by site is impossible without clustering.

**Decision.** Rebuild the split by clustering near-duplicates (group, then split by group) before any training; keep the official test set only as a secondary, leaky benchmark. Use a detector (YOLO) rather than the 224 classifier for the real model.

**Status.** `open`. **Evidence.** scripts used: label reader and dHash check (not versioned), results above.

## RES-CAM-3 — Near-duplicate groups and leak-free split of D-Fire (12 Nov 2026)
**Question.** How much do the official D-Fire splits leak, and what split can be trusted?

**Method.** `ai-data/tools/dedup_groups.py` on all 21 527 images: 64-bit difference hash (9×8 grayscale) plus a 4×4 RGB thumbnail; two images are linked when Hamming ≤ h and the mean thumbnail difference ≤ c; groups = connected components; whole groups are assigned to one split (greedy, stratified on background / fire / smoke / both, 70/15/15, seed 0). Three threshold pairs tried.

**Result.**
| Thresholds (h, c) | Linked groups | Largest group | val / test images sharing a group with the official train |
|---|---|---|---|
| 2, 8 | 13 513 | 711 | 40 % / 40 % |
| 4, 12 | 11 775 | 982 | 47 % / 49 % |
| 6, 16 | 10 519 | 1 308 | 53 % / 54 % |
- New split `ai-data/data/vision_split/split_v2.csv` (built with 6, 16, the loosest): train 15 068, val 3 230, test 3 229; fire-only images 815 / 175 / 174; 10 538 images changed split.
- After the new split, no val or test image shares a group with train under any of the three thresholds (0.0 %).

**Reading.**
- Roughly half of the official val and test images have a near-duplicate in train, so scores on the official split overstate performance. The earlier sample estimate (36 %) was lower because only 18 % of train was hashed.
- Zero leakage is relative to this hash. Frames of one video further apart than the thresholds, or the same site shot at another time, are not linked. Site-level leakage is not excluded (no site id exists). Chaining may merge unrelated scenes in the largest groups (not inspected).
- Counts are small for fire-only images in val and test (about 175): metrics for that class carry wide intervals.

**Decision.** Train, tune and select on `split_v2`; keep the official test as a secondary benchmark labelled as leaky. Next: inspect the largest groups visually, add hard negatives and OV2640 frames.

**Status.** `kept`, `open` (site-level leakage). **Evidence.** `python ai-data/tools/dedup_groups.py features|cluster|split` (see the file header).

## RES-CAM-4 — Shortcuts in D-Fire, OV2640 degradations, YOLO adapter and decision metrics (12 Nov 2026)
**Question.** Before any training: what can a network learn in D-Fire that will not transfer to the box camera, and which tools are needed to measure the real decision quality?

**Method.** Mean luminance of every image from the 4×4 thumbnails (21 527 images), image-level class from the labels; visual check of the degradations on real images; unit tests of the tools; hand-made detector outputs for the adapter.

**Result.**
| Image class | Images | Dark (luminance < 40) | Bright (> 110) |
|---|---|---|---|
| background | 9 838 | 7 % | 38 % |
| smoke only | 5 867 | 2 % | 54 % |
| fire only | 1 164 | **62 %** | 9 % |
| fire + smoke | 4 658 | 28 % | 26 % |
- Among dark images, 76 % contain fire or smoke (54 % over the whole set): a detector can score well by learning "dark with a bright spot = fire".
- Frames come from fixed surveillance cameras and many carry a `CameraXXXX` label and a date stamp: a possible second shortcut (measured in RES-CAM-6; the first estimate of its size, 12 % of background frames, was wrong and is corrected there).
- Added in `ai-data/gateway/vision/train/`: `degrade.py` (resolution loss, blur, white balance and gamma, vignetting, haze, dirt, sensor noise, JPEG; plus sun-flare and night-like darkening reserved for background images, as synthetic hard negatives), `build_degraded.py`, `make_lists.py`, `train.py` (two phases, light hue), `predict_scores.py`, `evaluate.py` (AUC, average precision, false-positive rate at a target recall, false alarms per day, 95 % bootstrap intervals over near-duplicate groups, dark / day slices). The `split_v2.csv` now carries the luminance.
- Gateway: `gateway_vision/yolo.py` (letterbox, decode, NMS, image-level rule), served by the same HTTP service.
- Tests: 12 on the degradations, metrics and adapter (degradations deterministic and monotonic in severity; ≤ 10 % of degraded frames refused by the box quality check; AUC and false-positive rate equal the Gaussian theory; the group bootstrap interval is wider on duplicated frames; box mapped back to the original image; NMS keeps different classes; the adapter works inside the real HTTP service).

**Reading.**
- The degradation ranges are assumptions, not a fitted model of the OV2640. The night-like darkening is a gain and a colour cast, not a physical night image.
- `evaluate.py` was run only on invented scores to check the plumbing; **no detector was trained, so there is no detection result**.
- False alarms per day depend on the assumed number of photos per no-fire scene (default 2 880, one per 30 s all day, a worst case).

**Decision.** Train with night-like negatives and degraded copies; always report the dark slice. Before trusting a score, add a masked-overlay evaluation and a test on real OV2640 frames. Next steps: SPRT fusion of repeated frames on the gateway, calibration, INT8 export for the VIM4.

**Status.** `open`. **Evidence.** `cd ai-data/gateway/vision/train && python -m pytest tests`; `cd ../python && python -m pytest`.

**Addendum RES-CAM-4 (12 Nov, evening) — end-to-end smoke test with PyTorch.** Ultralytics 8.4.211 and PyTorch 2.15 (CPU) installed in the cloud container; `train.py --smoke` run on a synthetic 720-image set (320 px, 1 epoch per phase), then the adapter run on the exported ONNX.
- Chain verified: list merge, phase 1 (frozen backbone), phase 2, ONNX export; output `[1, 6, 2100]`, class names `{0: 'smoke', 1: 'fire'}` read from the model metadata; `gateway_vision.yolo` decodes it.
- **Bug found and fixed:** the merged training list was written with a path relative to the dataset root and not found (`d["train"]` now absolute).
- Nothing about detection quality: one training step on synthetic rectangles. The `onnxslim` warning at export is harmless (`pip install onnxslim`).
- The adapter was run on the real export from a working copy outside the repo, not from the repo package.

## RES-CAM-5 — Calibration and sequential evidence over repeated photos (12 Nov 2026)
**Question.** Can the gateway cut false alarms by accumulating evidence over the photos of a box (one per 30 s in Suspicion) instead of trusting one image?

**Method.** `gateway_vision/evidence.py`: Platt calibration of detector scores (logistic on the logit of the score, fitted on validation) with expected calibration error; Wald's SPRT on per-frame log-likelihood ratios, with an evidence floor and a damping factor. Tested on synthetic scores and Gaussian log-likelihood ratios (17 tests in the package, 5 of them on this module).

**Result.**
- Calibration recovers the true parameters (a = 3.0, b = −1.0 within 0.15) and brings ECE under 0.02 where the raw scores are far above (synthetic, mis-calibrated by construction).
- Independent frames: Wald's bounds hold (alpha = 1 %, beta = 10 %; measured false alarms ≤ 1.5 %, misses ≤ 13 %) and the decision takes fewer than 20 frames on average.
- **Correlated frames (shared scene bias, correlation 0.8): the false-alarm rate rises to about 24 % for a 1 % target.** Damping each frame (rho = 0.15) lowers it to about 11 %, still 11 times the target.
- Without a floor on the evidence, a long quiet period makes the test stop on "no fire" before a later real fire (the floor fixes it in the test).

**Reading.**
- Accumulating photos helps only if errors are independent. A persistent misreading (red roof, lights, sunset) repeats in every photo and accumulates as if it were proof. Damping is not a cure.
- All numbers are from simulations: no detector, no real sequence. The correlation value and the damping factor must be fitted on real sequences from the box camera.
- A real remedy has to use change over time (a static look-alike stays identical, smoke and flames evolve) and a per-site memory of confirmed false alarms. Neither is implemented or validated: no data.

**Decision.** Use the SPRT only with a floor and a conservative damping; do not claim the per-scene false-alarm rate from the independent-frame bound. Collect repeated photos of fixed no-fire scenes (several hours, sun, wind, lights) with the real camera to measure the correlation before fixing alpha.

**Status.** `open`. **Evidence.** `cd ai-data/gateway/vision/python && python -m pytest tests/test_evidence.py`.

## RES-CAM-6 — Burned-in camera label and date stamp in D-Fire: size of the shortcut and tools (12 Nov 2026)
**Question.** Do the `CameraNNNN` label and the date stamp burned into D-Fire frames predict the class, and can they be neutralised?

**Method.** `train/overlay_probe.py` on a random 5 000-image sample of all three splits (4 587 images read, seed 0): the stamp boxes (label x 4.5-16 %, y 8-11.5 %; date x 81-99 %, y 88-91.5 % of a 1280×720 frame) are tested for a black box with white text. Geometry read off real frames and checked visually on montages. `train/overlay.py` masks the regions or pastes a synthetic stamp.

**Result.**
| Image class | Images | With a stamp |
|---|---|---|
| background | 2 277 | 30.5 % |
| smoke only | 1 308 | 24.9 % |
| fire only | 257 | 44.4 % |
| fire + smoke | 1 158 | 16.9 % |
- Overall 27 % of the frames carry a stamp. P(fire or smoke | stamp) = 0.48 against 0.57 without: the stamp does not announce an alarm. For fire-only images it is more frequent (44 % against 30 % for background).
- Among dark images, 59 % carry a stamp; P(positive | dark, stamp) = 0.79 and P(positive | dark, no stamp) = 0.73: small difference.
- **Correction:** a first version of the probe used regions much larger than the stamps and reported 12 % for background, 5 % for smoke-only and a much stronger link to fire. That was a detection error (the 50 % black-pixel test failed on boxes smaller than the region), found when the montage showed stamps on frames the probe called clean.
- Tools: `mask_overlay` fills the stamp regions with the mean colour of a ring around them; `paste_overlay` draws a stamp that looks like the real one (checked visually); `build_degraded.py` masks 35 % of the stamped training frames and pastes a stamp on 25 % of the others, with the same probabilities for every class; `predict_scores.py --mask-overlay` scores masked images and writes an `overlay` column; `evaluate.py` reports the overlay and no-overlay slices. 13 tests in `train/tests` pass.

**Reading.**
- The stamp is a weak shortcut for the two-class decision (alarm or not) and a mild one for fire-only; darkness (RES-CAM-4) is the larger one. Counts are from a sample of 4 587 to 5 000 images; only 257 fire-only frames, so those percentages carry a wide margin (about ±6 points).
- Detection of the stamp relies on assumed boxes that hold for 1280×720 frames of the Brazilian cameras; other cameras and resolutions (a small top-left text line on some) are only partly covered by the mask.
- The scoring tools ran with a constant fake detector (plumbing only): no model was trained, so the masked-against-unmasked comparison has not been made.

**Decision.** Keep the stamp randomisation in training (cheap) and the masked evaluation as a required check: a score drop on the "with overlay" slice after masking means the model relied on it.

**Status.** `open`. **Evidence.** `cd ai-data/gateway/vision/train && python overlay_probe.py ... && python -m pytest tests`.


## RES-CAM-7 - Notebook de fine-tuning YOLO sur GPU et client d'envoi de photos (test de la chaine)

- **Question** : la chaine complete (GPU, poids, donnees, traitement d'images, entrainement, export ONNX, evaluation, service gateway, envoi de photos) tient-elle dans un seul notebook executable par une personne seule ?
- **Methode** : `ai-data/gateway/vision/train/notebooks/01_finetune_yolo.ipynb` (presets smoke / quick / full). Execute de bout en bout en preset `smoke` sur un jeu synthetique de meme structure que D-Fire (360 images, CPU, YOLOv8n, 1 epoch par phase). Aucun GPU disponible pendant ce test.
- **Resultat** :
  - la chaine s'execute sans erreur : controle GPU, poids, controle d'integrite, copies degradees, entrainement deux phases, export ONNX, scores, seuils, calibration, controle ONNX contre PyTorch (ecart 0.000), service + 12 photos envoyees avec le client (temps modele ~100 ms, aller-retour ~110 ms sur CPU de test) ;
  - le controle GPU arrete bien le notebook sans CUDA (message avec la commande `pip` a utiliser) ;
  - **echec trouve par le test** : les listes d'images utilisaient des chemins relatifs a la racine des donnees, qu'Ultralytics ne resout pas (toutes les images de validation ignorees comme corrompues). Corrige : `make_lists.py` ecrit des chemins absolus (le test `test_degrade` lisait les listes avec `split()`, casse par l'espace de "fire detection" : remplace par `splitlines()`) ;
  - le modele smoke est degenere (scores constants a 1.0, AUC 0.5) : attendu avec 3 images et 1 epoch. Le notebook affiche maintenant une alerte si les scores sont constants.
- **Lecture** : le test valide la plomberie, **pas la qualite du modele**. Aucun resultat de detection n'existe encore.
- **Decision** : lancer `PRESET = "smoke"` sur le PC GPU, puis `"full"` ; comparer n / s / m sur les fausses alertes par jour a rappel fixe, puis mesurer la latence sur la VIM4. Pas de resultat chiffre avant ce run.
- **Limites** : memes limites que RES-CAM-3 a 6 (aucune image OV2640 reelle, degradations supposees, fuite par site non exclue). Licence Ultralytics AGPL-3.0 a signaler a l'equipe.
