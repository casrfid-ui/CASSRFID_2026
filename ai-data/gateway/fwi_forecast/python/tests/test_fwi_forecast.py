import time
import numpy as np
import pytest

from fwi_forecast import Climate, FwiForecaster, experiments as E


@pytest.fixture(scope="module")
def world():
    ss = E.seasons(12, seed=5)
    return ss, Climate.fit(ss[:8])


def test_oracle_consistency(world):
    ss, _ = world
    s = ss[9]
    for i in (40, 80, 120):
        assert np.max(np.abs(E.oracle(s, i) - s["fwi"][i + 1:i + 4])) <= 1e-9


def test_climate_json_roundtrip(world):
    _, c = world
    c2 = Climate.from_json(c.to_json())
    assert np.allclose(c.mean["temp"], c2.mean["temp"]) and c.gamma == c2.gamma


def test_forecast_shape_and_order(world):
    ss, c = world
    s = ss[9]; i = 100
    fc = FwiForecaster(c, 100, seed=1).forecast((s["ffmc"][i], s["dmc"][i], s["dc"][i]),
                                                {k: s[k][i] for k in ("temp", "rh", "wind", "rain")}, int(s["doy"][i]))
    assert len(fc) == 3
    for d in fc:
        assert d["q10"] <= d["q50"] <= d["q90"] and 0 <= d["p_high"] <= 1


def test_runtime_under_100ms(world):
    ss, c = world
    s = ss[9]; i = 100
    f = FwiForecaster(c, 100, seed=1)
    args = ((s["ffmc"][i], s["dmc"][i], s["dc"][i]), {k: s[k][i] for k in ("temp", "rh", "wind", "rain")}, int(s["doy"][i]))
    f.forecast(*args)
    t0 = time.perf_counter(); f.forecast(*args); dt = time.perf_counter() - t0
    assert dt < 0.1, dt


def test_external_forecast_replaces_ensemble(world):
    ss, c = world
    s = ss[9]; i = 100
    ext = [tuple(float(s[k][i + j]) for k in ("temp", "rh", "wind", "rain")) for j in (1, 2, 3)]
    fc = FwiForecaster(c).forecast((s["ffmc"][i], s["dmc"][i], s["dc"][i]), {k: s[k][i] for k in ("temp", "rh", "wind", "rain")}, int(s["doy"][i]), external=ext)
    assert abs(fc[0]["q50"] - s["fwi"][i + 1]) < 1e-9 and fc[0]["q10"] == fc[0]["q90"]
