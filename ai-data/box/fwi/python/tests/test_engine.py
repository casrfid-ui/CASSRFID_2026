import pytest

from fwi import FwiEngine, danger_class, mode_for_class


@pytest.mark.parametrize("value,cls", [(0, 0), (5.1, 0), (5.2, 1), (11.2, 2), (21.3, 3), (37.9, 3), (38, 4), (50, 5), (400, 5)])
def test_effis_classes(value, cls):
    assert danger_class(value) == cls


def test_mode_follows_class():
    assert [mode_for_class(c) for c in range(6)] == ["eco"] * 3 + ["alert"] * 3


def hot_dry_day(engine, days, month=7):
    out = None
    for h in range(24 * days):
        hr = h % 24
        out = engine.update_hour(hr, month, 36.0 if 10 <= hr <= 18 else 25.0, 18.0 if 10 <= hr <= 18 else 50.0, 20.0, 0.0)
    return out


def test_hot_dry_spell_reaches_alert():
    assert hot_dry_day(FwiEngine(), 10).mode == "alert"


def test_rain_resets_toward_eco():
    e = FwiEngine()
    hot_dry_day(e, 10)
    out = None
    for h in range(24 * 3):
        out = e.update_hour(h % 24, 7, 15.0, 98.0, 5.0, 3.0)
    assert out.mode == "eco"


def test_dmc_dc_move_once_per_day_at_noon():
    e = FwiEngine()
    seen = set()
    for h in range(24):
        o = e.update_hour(h, 7, 30.0, 30.0, 10.0, 0.0)
        seen.add((round(o.dmc, 6), round(o.dc, 6)))
        if h < 12:
            assert o.dmc == 6.0 and o.dc == 15.0
    assert len(seen) == 2


def test_daily_rain_window_is_24_hours():
    e = FwiEngine()
    for h in range(24):
        e.update_hour(h, 7, 20.0, 60.0, 5.0, 2.0 if h == 3 else 0.0)
    assert sum(e.state.rain_last_24h) == 2.0
