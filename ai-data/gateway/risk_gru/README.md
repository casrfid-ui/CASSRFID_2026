# risk_gru — GRU ignition risk (day +1, +2, +3)

**Status.** Implemented, tested, evaluated on synthetic seasons and on the Algerian data set; results and decision in `../../docs/research/gateway-risk-gru.md`.

- Design and pass criteria (written before running): [`FICHE.md`](FICHE.md)
- Research log, including failures: `ai-data/docs/research/gateway-risk-gru.md`
- Run-time class (on the gateway): `risk_gru.RiskPredictor(model_path).update(day_dict)` — numpy only, ≈ 0.2 ms.
- Demo model: `models/risk_gru_demo_synthetic.npz` (16 KB, 1 491 parameters, synthetic data only).
- Notebooks (stored outputs, step-by-step explanation): `python/notebooks/01_data_and_features.ipynb`, `python/notebooks/02_training_and_evaluation.ipynb`; their sources are percent-format scripts in `python/notebooks/src/` (rebuild with `ai-data/tools/nb_from_py.py`).
- Training / demo-model script: `python/scripts/make_demo_model.py` (needs torch + scikit-learn)

## Run the tests
```bash
cd ai-data/gateway/risk_gru/python
PYTHONPATH=python/src:../common/python/src:../../box/fwi/python/src python -m pytest tests -q
```
(or `pip install -e .[dev]`; tests that need PyTorch are skipped when it is absent).

## Rules of this folder
Evidence level is stated in every result (S synthetic, A small real data set, P target-region data). A demo model is trained only to exercise the code path; it is never presented as a result.
