# fwi_forecast — FWI forecast, 1–3 days, with uncertainty

**Status.** Implemented, tested, evaluated. Beats persistence on synthetic seasons; evaluated on real weather; details in `../../docs/research/gateway-fwi-forecast.md`.

- Design and pass criteria (written before running): [`FICHE.md`](FICHE.md)
- Research log, including failures: `ai-data/docs/research/gateway-fwi-forecast.md`
- Run-time class (on the gateway): `fwi_forecast.FwiForecaster(Climate.from_json(...)).forecast(state, today, doy)` — numpy + the box engine, ≈ 3 ms for 100 members.
- Demo model: `models/fwi_climate_synthetic.json` (climate fitted on synthetic seasons; refit on site data for real use).
- Notebooks (stored outputs, step-by-step explanation): `python/notebooks/01_engine_and_method.ipynb`, `python/notebooks/02_evaluation.ipynb`; their sources are percent-format scripts in `python/notebooks/src/` (rebuild with `ai-data/tools/nb_from_py.py`).
- Training / demo-model script: `python/scripts/make_demo_climate.py` (numpy only); the boosting comparison needs scikit-learn

## Run the tests
```bash
cd ai-data/gateway/fwi_forecast/python
PYTHONPATH=python/src:../common/python/src:../../box/fwi/python/src:../risk_gru/python/src python -m pytest tests -q
```
(or `pip install -e .[dev]`; tests that need PyTorch are skipped when it is absent).

## Rules of this folder
Evidence level is stated in every result (S synthetic, A small real data set, P target-region data). A demo model is trained only to exercise the code path; it is never presented as a result.
