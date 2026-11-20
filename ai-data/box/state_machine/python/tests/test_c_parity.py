"""The C port (../c) must take the same decisions as this Python reference on long random input streams
(all inputs, resets, irregular time steps). Skipped when no C compiler is available."""
import pathlib
import random
import shutil
import subprocess

import pytest

from state_machine import Inputs, StateMachine

C_DIR = pathlib.Path(__file__).resolve().parents[2] / "c"
pytestmark = pytest.mark.skipif(not (shutil.which("make") and shutil.which("cc")), reason="no C toolchain")
LABELS = {"background": 0, "fire": 1, "smoke": 2}
KIND = {"alert": 1, "state_change": 2, "heartbeat": 3, "last_gasp": 4}


@pytest.fixture(scope="module")
def cli(tmp_path_factory):
    build = tmp_path_factory.mktemp("cbuild")
    subprocess.run(["make", "-C", str(C_DIR), f"BUILD={build}", "cli"], check=True, capture_output=True)
    return str(build / "sm_cli")


def stream(seed, n, p_event):
    """Random inputs with bursts, so that every state, the hold timer and the survival mode are visited."""
    rng = random.Random(seed)
    burst = 0
    items = []
    for _ in range(n):
        if burst == 0 and rng.random() < p_event:
            burst = rng.randint(1, 40)
        burst = max(0, burst - 1)
        active = burst > 0
        cam = None
        if rng.random() < (0.3 if active else 0.02):
            cam = (rng.choice(["fire", "smoke", "background"]), rng.choice([0.3, 0.59, 0.6, 0.61, 0.95]))
        items.append(dict(
            gas_smoke=active and rng.random() < 0.8, gas_fault=rng.random() < 0.01,
            flame=active and rng.random() < 0.5 or rng.random() < 0.01, camera=cam,
            fwi_mode=rng.choice(["eco", "alert"]), fwi_danger=rng.randint(0, 5),
            battery_low=rng.random() < 0.03 or (bool(items) and items[-1]["battery_low"] and rng.random() < 0.8),
            housing_hot=rng.random() < 0.002, supply_fault=rng.random() < 0.002,
            dt_s=rng.choice([10.0, 27.3, 30.0, 300.0, 600.0, 1500.0, 3600.0]),
            reset=rng.random() < 0.005))
    return items


def to_line(it):
    cam = it["camera"]
    return " ".join(str(v) for v in (
        int(it["gas_smoke"]), int(it["gas_fault"]), int(it["flame"]), int(cam is not None),
        LABELS[cam[0]] if cam else 0, repr(cam[1] if cam else 0.0), int(it["fwi_mode"] == "alert"), it["fwi_danger"],
        int(it["battery_low"]), int(it["housing_hot"]), int(it["supply_fault"]), repr(it["dt_s"])))


def py_line(o):
    fr = [v for f in o.frames for v in (KIND[f[0]], f[1])]
    return [o.state, o.interval_s, int(o.camera_on), int(o.gps_on), int(o.actuator), o.reasons, int(o.last_gasp),
            len(o.frames), *fr]


@pytest.mark.parametrize("seed,p_event", [(1, 0.01), (2, 0.05), (3, 0.002), (4, 0.2)])
def test_random_streams(cli, seed, p_event):
    items = stream(seed, 6000, p_event)
    sm, expected, lines = StateMachine(), [], []
    for it in items:
        if it["reset"]:
            sm.reset()
            lines.append("RESET")
        x = Inputs(**{k: v for k, v in it.items() if k != "reset"})
        expected.append(py_line(sm.step(x)))
        lines.append(to_line(it))
    out = subprocess.run([cli], input="\n".join(lines) + "\n", capture_output=True, text=True, check=True).stdout
    got = [[float(v) for v in ln.split()] for ln in out.splitlines()]
    assert len(got) == len(expected)
    for i, (g, e) in enumerate(zip(got, expected)):
        assert g == pytest.approx(e, abs=1e-12), f"step {i}"
    states = {int(g[0]) for g in got}
    assert states == {0, 1, 2}, "the stream must visit every state"
