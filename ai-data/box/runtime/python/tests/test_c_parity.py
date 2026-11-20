"""The C runtime must give the same numbers as this Python chain of the three blocks, tick by tick, on the real
BME688 sample replayed at its own pace (27 s) and at the Eco pace (300 s, 45 days), with random weather, rain,
flame, camera, battery and supervision events. Skipped when no C compiler is available."""
import pathlib
import random
import shutil
import subprocess

import numpy as np
import pytest

from box_runtime import BoxRuntime, Tick
from gas_chain import data_mendeley as dm

C_DIR = pathlib.Path(__file__).resolve().parents[2] / "c"
pytestmark = pytest.mark.skipif(not (shutil.which("make") and shutil.which("cc")), reason="no C toolchain")
LABELS = {"background": 0, "fire": 1, "smoke": 2}
KIND = {"alert": 1, "state_change": 2, "heartbeat": 3, "last_gasp": 4}
T0 = 1784073600 + 5 * 3600 + 17 * 60          # 2026-07-15 05:17 UTC


@pytest.fixture(scope="module")
def cli(tmp_path_factory):
    build = tmp_path_factory.mktemp("cbuild")
    subprocess.run(["make", "-C", str(C_DIR), f"BUILD={build}", "cli"], check=True, capture_output=True)
    return str(build / "box_cli")


def burst(rng):
    """8 digital reads, active low: a dark scene with glitches, or a lit one."""
    p = rng.choice([0.05, 0.3, 0.9])
    return tuple(0 if rng.random() < p else 1 for _ in range(8))


def timeline(pace, seed, max_scans=None):
    d = dm.load_sample()
    rng = random.Random(seed)
    n = len(d["gas"]) if max_scans is None else min(max_scans, len(d["gas"]))
    u, ticks = T0, []
    battery = 0
    for i in range(n):
        u += max(1, int(round(d["dt"][i] * pace)))
        hr = (u // 3600) % 24
        day = u // 86400
        hot = np.cos(2 * np.pi * (hr - 15) / 24)
        weather = (22 + 10 * hot + 3 * np.sin(day), min(100.0, max(8.0, 40 - 25 * hot + 10 * np.sin(day / 2))),
                   max(0.0, 15 + 10 * hot + rng.gauss(0, 5)))
        battery = max(0, battery - 1)
        if rng.random() < 0.002:
            battery = rng.randint(3, 30)
        ticks.append(Tick(
            unix_s=u,
            weather=weather if rng.random() < 0.97 else None,
            rain_mm=rng.choice([0.2, 1.0, 4.0]) if rng.random() < 0.01 else 0.0,
            gas=(d["gas"][i], d["temp"][i], d["rh"][i]) if rng.random() < 0.98 else None,
            flame=rng.random() < 0.01,
            flame_raw=burst(rng) if rng.random() < 0.2 else None,
            camera=(rng.choice(["fire", "smoke", "background"]), rng.choice([0.4, 0.6, 0.9])) if rng.random() < 0.01 else None,
            battery_low=battery > 0, housing_hot=rng.random() < 0.0005, supply_fault=rng.random() < 0.0005))
    return ticks


def to_line(t):
    w = t.weather or (0.0, 0.0, 0.0)
    g = t.gas or (np.ones(10), np.ones(10), np.ones(10))
    cam = t.camera
    nums = [t.unix_s, int(t.weather is not None), *map(repr, map(float, w)), repr(t.rain_mm), int(t.gas is not None),
            *(repr(float(v)) for arr in g for v in arr), int(t.flame), int(cam is not None),
            LABELS[cam[0]] if cam else 0, repr(cam[1] if cam else 0.0), int(t.battery_low), int(t.housing_hot),
            int(t.supply_fault)]
    if t.flame_raw is not None:
        nums += [len(t.flame_raw), *t.flame_raw]
    return " ".join(str(v) for v in nums)


def expected_row(o):
    fr = [v for f in o.sm.frames for v in (KIND[f[0]], f[1])]
    f = o.fwi
    return ([o.sm.state, o.sm.interval_s, int(o.sm.camera_on), int(o.sm.gps_on), int(o.sm.actuator), o.sm.reasons,
             int(o.sm.last_gasp), len(o.sm.frames), *fr],
            [int(o.fwi_updated), f["danger"], 1 if f["mode"] == "alert" else 0, f["fwi"], f["ffmc"], f["dmc"], f["dc"]],
            [int(o.gas_scanned), o.gas_cls, o.gas_score, int(o.gas_warmup)])


def parse(line):
    return [[float(v) for v in part.split()] for part in line.split("|")]


@pytest.mark.parametrize("pace,seed,max_scans", [(1, 1, 2500), (11, 2, None)])
def test_replay_matches_python(cli, pace, seed, max_scans):
    ticks = timeline(pace, seed, max_scans)
    ref = BoxRuntime()
    expected = [expected_row(ref.step(t)) for t in ticks]
    out = subprocess.run([cli, "0"], input="\n".join(to_line(t) for t in ticks) + "\n", capture_output=True,
                         text=True, check=True).stdout.splitlines()
    assert len(out) == len(expected)
    seen = set()
    for i, (line, exp) in enumerate(zip(out, expected)):
        got = parse(line)
        for g, e in zip(got, exp):
            assert g == pytest.approx(e, abs=1e-9), f"tick {i}"
        seen.add(int(got[0][0]))
    fwi_updates = sum(e[1][0] for e in expected)
    assert fwi_updates >= (3 if pace == 1 else 150)
    assert {0, 1} <= seen                                       # the replay must reach Suspicion


def test_local_time_offset(cli):
    ticks = timeline(11, 3, 1500)
    ref = BoxRuntime(utc_offset_s=2 * 3600)
    expected = [expected_row(ref.step(t)) for t in ticks]
    out = subprocess.run([cli, str(2 * 3600)], input="\n".join(to_line(t) for t in ticks) + "\n",
                         capture_output=True, text=True, check=True).stdout.splitlines()
    for i, (line, exp) in enumerate(zip(out, expected)):
        for g, e in zip(parse(line), exp):
            assert g == pytest.approx(e, abs=1e-9), f"tick {i}"
