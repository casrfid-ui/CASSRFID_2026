# spread_source — Fire spread isochrones + smoke source localisation

**Status.** Implemented, tested. Geometry and numerics verified; fuel parameters use default values, calibrated per site; source localisation is used when at least 4 boxes sit in the plume, otherwise the drone targets the detecting box.

- Design and pass criteria (written before running): [`FICHE.md`](FICHE.md)
- Research log, including failures: `ai-data/docs/research/gateway-spread-source.md`
- Run-time class (on the gateway): `FireSpread(...).arrival(...)`, `SourceLocator(...).posterior(...)` — numpy only, 0.04 s for a 100×100 grid.
- Model: physics + Bayesian inversion, no training needed.
- Notebooks (stored outputs, step-by-step explanation): `python/notebooks/01_fire_spread.ipynb`, `python/notebooks/02_plume_and_source.ipynb`; their sources are percent-format scripts in `python/notebooks/src/` (rebuild with `ai-data/tools/nb_from_py.py`).
- Training / demo-model script: none

## Run the tests
```bash
cd ai-data/gateway/spread_source/python
PYTHONPATH=python/src:../common/python/src python -m pytest tests -q
```
(or `pip install -e .[dev]`; tests that need PyTorch are skipped when it is absent).

## Rules of this folder
Evidence level is stated in every result (S synthetic, A small real data set, P target-region data). A demo model is trained only to exercise the code path; it is never presented as a result.
