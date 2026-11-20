"""Fits the climate of the forecaster on SYNTHETIC seasons and writes models/fwi_climate_synthetic.json.
On the real gateway, refit from the site's own history (at least 3 seasons) or from ERA5 daily data."""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent / "src"), str(HERE.parents[2] / "common/python/src"), str(HERE.parents[3] / "box/fwi/python/src"), str(HERE.parents[2] / "risk_gru/python/src")]
from fwi_forecast import Climate, experiments as E  # noqa: E402

if __name__ == "__main__":
    c = Climate.fit(E.seasons(40, seed=11))
    out = HERE.parents[1] / "models" / "fwi_climate_synthetic.json"
    out.write_text(c.to_json())
    print(out, out.stat().st_size, "bytes")
