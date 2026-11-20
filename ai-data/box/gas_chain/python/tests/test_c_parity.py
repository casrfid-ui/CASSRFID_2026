"""The C port (../c) must give the same numbers as this Python reference, scan by scan.
Sequences: the real BME688 sample (every episode), injected faults (out-of-range burst, stuck stretch, spike, slow
drift, NaN), and a restore from a saved baseline. Skipped when no C compiler is available."""
import pathlib
import shutil
import subprocess

import numpy as np
import pytest

from gas_chain import GasChain
from gas_chain import data_mendeley as dm

C_DIR = pathlib.Path(__file__).resolve().parents[2] / "c"
pytestmark = pytest.mark.skipif(not (shutil.which("make") and shutil.which("cc")), reason="no C toolchain")


@pytest.fixture(scope="module")
def cli(tmp_path_factory):
    build = tmp_path_factory.mktemp("cbuild")
    subprocess.run(["make", "-C", str(C_DIR), f"BUILD={build}", "cli"], check=True, capture_output=True)
    return str(build / "gc_cli")


def py_rows(chain, gas, temp, rh, dt):
    rows = []
    for i in range(len(gas)):
        r = chain.update(gas[i], temp[i], rh[i], dt[i])
        rows.append([r.score, r.cls, r.faults, r.warmup, r.scan_bad, r.depth, r.peak_step, *r.bands])
    return np.array(rows, float)


def c_rows(cli, gas, temp, rh, dt, restore=None):
    lines = []
    if restore is not None:
        lines.append("R " + " ".join(repr(float(v)) for v in restore))
    for i in range(len(gas)):
        vals = [*gas[i], *temp[i], *rh[i], dt[i]]
        lines.append(" ".join(repr(float(v)) for v in vals))
    out = subprocess.run([cli], input="\n".join(lines) + "\n", capture_output=True, text=True, check=True).stdout
    return np.array([[float(x) for x in ln.split()] for ln in out.splitlines()])


def same(a, b):
    assert a.shape == b.shape
    np.testing.assert_allclose(a, b, rtol=0, atol=1e-9)         # discrete columns (class, flags, step) are exact


@pytest.fixture(scope="module")
def sample():
    return dm.load_sample()


def test_every_real_episode(cli, sample):
    for e in np.unique(sample["episode"]):
        m = sample["episode"] == e
        g, t, h, dt = (sample[k][m] for k in ("gas", "temp", "rh", "dt"))
        same(py_rows(GasChain(), g, t, h, dt), c_rows(cli, g, t, h, dt))


def test_injected_faults(cli, sample):
    m = sample["episode"] == np.unique(sample["episode"])[0]
    g, t, h, dt = (sample[k][m].copy() for k in ("gas", "temp", "rh", "dt"))
    g[60:64] = 5.0                                   # out-of-range burst
    g[100:115] = g[99]                               # stuck stretch
    g[150, :] *= 0.2                                 # lone spike
    g[200:] *= np.exp(-0.0004 * np.arange(len(g) - 200))[:, None]      # slow drift
    g[300, 4] = np.nan                               # NaN reading
    t[310, 0] = 90.0                                 # temperature out of range
    h[320, 9] = 101.0                                # humidity out of range
    py, c = py_rows(GasChain(), g, t, h, dt), c_rows(cli, g, t, h, dt)
    same(py, c)
    assert py[:, 4].sum() >= 7 and (py[:, 2].astype(int) & 2).any() and (py[:, 1] == 3).any()   # the faults were seen


def test_restore_from_saved_baseline(cli, sample):
    m = sample["episode"] == np.unique(sample["episode"])[1]
    g, t, h, dt = (sample[k][m] for k in ("gas", "temp", "rh", "dt"))
    first = GasChain()
    py_rows(first, g[:40], t[:40], h[:40], dt[:40])
    base = first.snapshot()
    chain = GasChain()
    chain.restore(base)
    same(py_rows(chain, g[40:], t[40:], h[40:], dt[40:]), c_rows(cli, g[40:], t[40:], h[40:], dt[40:], restore=base))


def test_irregular_time_steps(cli, sample):
    m = sample["episode"] == np.unique(sample["episode"])[2]
    g, t, h = (sample[k][m] for k in ("gas", "temp", "rh"))
    dt = np.random.default_rng(1).choice([30.0, 300.0, 3600.0, 27.3], len(g))
    same(py_rows(GasChain(), g, t, h, dt), c_rows(cli, g, t, h, dt))
