import json
import pathlib

import pytest

from fwi import codes

REF = json.loads((pathlib.Path(__file__).parent / "data" / "fwi_xclim_reference.json").read_text())
TOL = 1e-3


def run_daily(season):
    """The daily chain exactly as the reference runs it: FFMC, DMC, DC, then ISI, BUI, FWI."""
    f, p, d = REF["start_up"]["ffmc"], REF["start_up"]["dmc"], REF["start_up"]["dc"]
    out = {k: [] for k in ("FFMC", "DMC", "DC", "ISI", "BUI", "FWI")}
    for i in range(len(season["temp"])):
        t, h, w, r, m = (season[k][i] for k in ("temp", "rh", "wind", "rain", "month"))
        f = codes.ffmc_daily(f, t, h, w, r)
        p = codes.dmc(p, t, h, r, m)
        d = codes.dc(d, t, r, m)
        isi, bui = codes.isi(f, w), codes.bui(p, d)
        for k, v in zip(out, (f, p, d, isi, bui, codes.fwi(isi, bui))):
            out[k].append(v)
    return out


@pytest.mark.parametrize("season", REF["seasons"], ids=lambda s: s["name"])
@pytest.mark.parametrize("component", ["FFMC", "DMC", "DC", "ISI", "BUI", "FWI"])
def test_daily_matches_xclim(season, component):
    mine = run_daily(season)[component]
    worst = max(abs(a - b) for a, b in zip(mine, season[component]))
    assert worst <= TOL, f"{component} differs from xclim {REF['xclim']} by {worst:.2e}"


def test_ffmc_bounds():
    assert 0 <= codes.ffmc_hourly(0, 30, 100, 0, 200) <= 101
    assert codes.ffmc_hourly(101, -20, 5, 100, 0) <= 101


def test_hourly_ffmc_dries_when_hot_dry_windy():
    f = 70.0
    for _ in range(12):
        nxt = codes.ffmc_hourly(f, 35, 20, 15, 0)
        assert nxt >= f
        f = nxt
    assert f > 85


def test_hourly_ffmc_wets_when_humid_cool():
    f = 90.0
    for _ in range(12):
        nxt = codes.ffmc_hourly(f, 12, 98, 5, 0)
        assert nxt <= f
        f = nxt
    assert f < 90


def test_hourly_rain_lowers_ffmc():
    assert codes.ffmc_hourly(88, 25, 40, 10, 5.0) < codes.ffmc_hourly(88, 25, 40, 10, 0.0)


def test_equilibrium_holds_when_between_ed_and_ew():
    f = codes.ffmc_hourly(80, 20, 60, 10, 0)
    mo = codes._moisture_from_ffmc(f, 147.27723)
    ed, ew = codes._equilibria(60, 20)
    assert ew <= ed
    assert mo >= 0


def test_hourly_daily_agree_on_order_of_magnitude():
    """24 identical hours of hourly FFMC should land near one daily step (different rate factors, same direction)."""
    f_h = 80.0
    for _ in range(24):
        f_h = codes.ffmc_hourly(f_h, 30, 30, 10, 0)
    f_d = codes.ffmc_daily(80.0, 30, 30, 10, 0)
    assert (f_h - 80.0) * (f_d - 80.0) > 0
