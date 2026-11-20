# gas_trend — Gas trend / early warning (GRU on the chain's outputs)

**Status.** Implemented, tested, evaluated on real recordings; results and decision in `../../docs/research/gateway-gas-trend.md`. Runs in the gateway slow path as a phase B model.

- Design and pass criteria (written before running): [`FICHE.md`](FICHE.md)
- Research log, including failures: `ai-data/docs/research/gateway-gas-trend.md`
- Run-time class (on the gateway): `gas_trend.TrendPredictor(model_path).update(score, depth, bands, temp, rh)` — numpy only, < 1 ms.
- Demo model: `models/gas_trend_demo.npz` (9 KB, 769 parameters; trained on the same 5 nodes the evaluation uses: no held-out evidence).
- Notebooks (stored outputs, step-by-step explanation): `python/notebooks/01_data_and_target.ipynb`, `python/notebooks/02_evaluation.ipynb`; their sources are percent-format scripts in `python/notebooks/src/` (rebuild with `ai-data/tools/nb_from_py.py`).
- Training / demo-model script: `python/scripts/make_demo_model.py` (needs torch + scikit-learn + pandas; reads the Mendeley CSV via `gas_chain.data_mendeley`)

## Run the tests
```bash
cd ai-data/gateway/gas_trend/python
PYTHONPATH=python/src:../common/python/src:../../box/gas_chain/python/src python -m pytest tests -q
```
(or `pip install -e .[dev]`; tests that need PyTorch are skipped when it is absent).

## Rules of this folder
Evidence level is stated in every result (S synthetic, A small real data set, P target-region data). A demo model is trained only to exercise the code path; it is never presented as a result.
