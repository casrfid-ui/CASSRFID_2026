"""The C port (../c) must give the same numbers as this Python reference.
Skipped when no C compiler is available."""
import json
import math
import pathlib
import random
import shutil
import subprocess

import pytest

from fwi import FwiEngine

HERE = pathlib.Path(__file__).parent
C_DIR = HERE.parents[1] / "c"
REF = json.loads((HERE / "data" / "fwi_xclim_reference.json").read_text())

pytestmark = pytest.mark.skipif(not (shutil.which("make") and shutil.which("cc")), reason="no C toolchain")


@pytest.fixture(scope="module")
def cli(tmp_path_factory):
    build = tmp_path_factory.mktemp("cbuild")
    subprocess.run(["make", "-C", str(C_DIR), f"BUILD={build}", "cli"], check=True, capture_output=True)
    return str(build / "fwi_cli")


def run(cli, args, lines):
    res = subprocess.run([cli, *args], input="\n".join(lines) + "\n", capture_output=True, text=True, check=True)
    return [line.split() for line in res.stdout.splitlines()]


def weather(hours, seed):
    """Two years of synthetic hourly weather incl. dry spells, storms and sensor extremes."""
    rng = random.Random(seed)
    rows = []
    for h in range(hours):
        day, hr = divmod(h, 24)
        month = min(12, 1 + (day % 365) * 12 // 365)
        season = math.cos(2 * math.pi * ((day % 365) - 200) / 365)
        diurnal = math.cos(2 * math.pi * (hr - 15) / 24)
        temp = 20 + 12 * season + 7 * diurnal + rng.gauss(0, 1.5)
        rh = min(100.0, max(5.0, 55 - 25 * season - 20 * diurnal + rng.gauss(0, 8)))
        wind = max(0.0, 12 + rng.gauss(0, 8) + 6 * diurnal)
        rain = rng.choice([2, 6, 15]) * rng.random() if rng.random() < (0.02 + 0.05 * (1 - season) / 2) else 0.0
        rows.append((hr, month, temp, rh, wind, rain))
    return rows


def fmt(row):
    return " ".join(repr(float(v)) if isinstance(v, float) else str(v) for v in row)


def python_reference(rows):
    e = FwiEngine()
    outs = []
    for hr, month, t, h, w, r in rows:
        o = e.update_hour(hr, month, t, h, w, r)
        outs.append([o.ffmc, o.dmc, o.dc, o.isi, o.bui, o.fwi, o.danger, 1 if o.mode == "alert" else 0])
    return outs


def assert_same(c_rows, py_rows, tol=1e-8):
    assert len(c_rows) == len(py_rows)
    for i, (c, p) in enumerate(zip(c_rows, py_rows)):
        for k in range(6):
            assert abs(float(c[k]) - p[k]) <= tol * max(1.0, abs(p[k])), f"hour {i} field {k}: C {c[k]} vs Python {p[k]}"
        assert int(c[6]) == p[6] and int(c[7]) == p[7], f"hour {i}: class/mode differ"


def test_hourly_engine_matches_python_over_two_years(cli):
    rows = weather(24 * 365 * 2, seed=7)
    assert_same(run(cli, ["hourly"], [fmt(r) for r in rows]), python_reference(rows))


def test_hourly_engine_matches_python_on_extremes(cli):
    rows = [(h % 24, 1 + (h // 24) % 12, t, rh, w, r)
            for h, (t, rh, w, r) in enumerate([(-30.0, 100.0, 0.0, 0.0), (45.0, 0.0, 120.0, 0.0), (10.0, 100.0, 0.0, 60.0),
                                               (40.0, 5.0, 80.0, 0.0), (0.0, 50.0, 5.0, 0.2)] * 200)]
    assert_same(run(cli, ["hourly"], [fmt(r) for r in rows]), python_reference(rows))


def test_history_flag_counts_real_hours(cli):
    rows = weather(40, seed=1)
    out = run(cli, ["hourly"], [fmt(r) for r in rows])
    assert [int(o[8]) for o in out] == [min(i + 1, 24) for i in range(40)]
    assert [int(o[9]) for o in out] == [1 if i < 23 else 0 for i in range(40)]


def test_restart_in_the_middle_changes_nothing(cli, tmp_path):
    rows = weather(24 * 60, seed=3)
    lines = [fmt(r) for r in rows]
    whole = run(cli, ["hourly"], lines)
    state = str(tmp_path / "fwi_state.bin")
    cut = 24 * 17 + 5                                    # restart at an arbitrary hour, rain in the window
    first = run(cli, ["hourly", state], lines[:cut])
    second = run(cli, ["hourly", state], lines[cut:])    # new process: state and 24 h rain come back from the file
    assert first + second == whole


@pytest.mark.parametrize("season", REF["seasons"], ids=lambda s: s["name"])
def test_daily_chain_matches_xclim(cli, season):
    s0 = REF["start_up"]
    lines = [fmt((season["temp"][i], season["rh"][i], season["wind"][i], season["rain"][i], int(season["month"][i])))
             for i in range(len(season["temp"]))]
    out = run(cli, ["daily", repr(s0["ffmc"]), repr(s0["dmc"]), repr(s0["dc"])], lines)
    for k, name in enumerate(("FFMC", "DMC", "DC", "ISI", "BUI", "FWI")):
        worst = max(abs(float(o[k]) - ref) for o, ref in zip(out, season[name]))
        assert worst <= 1e-3, f"C {name} differs from xclim by {worst:.2e}"
