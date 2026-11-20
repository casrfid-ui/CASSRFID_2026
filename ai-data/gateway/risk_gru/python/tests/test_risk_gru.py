import pathlib
import numpy as np
import pytest

from risk_gru import datasets, features, predictor

MODEL = pathlib.Path(__file__).resolve().parents[2] / "models" / "risk_gru_demo_synthetic.npz"


def test_synthetic_shapes_and_prevalence():
    X, Y, meta = features.build_windows(datasets.synthetic(n_years=6, seed=1, prevalence=0.06, variant="additive"))
    assert X.ndim == 3 and X.shape[1] == features.WINDOW and X.shape[2] == len(features.FEATURES)
    assert Y.shape == (len(X), len(features.HORIZONS))
    assert 0.02 < Y[:, 0].mean() < 0.15
    assert np.isfinite(X).all()


def test_algerian_label_handling():
    p = pathlib.Path(__file__).resolve().parents[4] / "data/algerian/Algerian_forest_fires_dataset_UPDATE.csv"
    if not p.exists():
        pytest.skip("Algerian CSV not present")
    tables = datasets.algerian(p)
    assert sum(np.isnan(t["fire"]).sum() for t in tables) == 1     # the one unlabeled day is kept as NaN ...
    X, Y, meta = features.build_windows(tables)
    assert np.isfinite(Y).all()          # no NaN label reaches the learner


def _day(dry, month=7):
    if dry:
        return dict(temp=36, rh=20, wind=25, rain=0.0, ffmc=94, dmc=120, dc=500, isi=18, bui=130, fwi=45, month=month)
    return dict(temp=18, rh=85, wind=5, rain=8.0, ffmc=60, dmc=10, dc=100, isi=1, bui=15, fwi=1, month=month)


@pytest.mark.skipif(not MODEL.exists(), reason="demo model not built")
def test_predictor_dry_is_riskier_than_wet():
    dry, wet = predictor.RiskPredictor(MODEL), predictor.RiskPredictor(MODEL)
    for _ in range(20):
        a, b = dry.update(_day(True)), wet.update(_day(False))
    assert 0 <= a["p_day1"] <= 1 and a["level"] in ("low", "moderate", "high")
    assert a["p_day1"] > b["p_day1"] and a["provisional"] is False


@pytest.mark.skipif(not MODEL.exists(), reason="demo model not built")
def test_missing_day_and_short_history_flagged():
    pr = predictor.RiskPredictor(MODEL)
    assert pr.update(_day(True))["provisional"] is True
    for _ in range(16):
        pr.update(_day(True))
    out = pr.update(None)
    assert out["missing_days"] == 1 and out["provisional"] is False
