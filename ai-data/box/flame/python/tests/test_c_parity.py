"""The C port (../c) must give the same results as this Python reference on random bursts:
all lengths 1..32 (and the refused 0 and 33), both polarities, several vote ratios and flicker limits.
Skipped when no C compiler is available."""
import pathlib
import random
import shutil
import subprocess

import pytest

from flame import Config, process

C_DIR = pathlib.Path(__file__).resolve().parents[2] / "c"
pytestmark = pytest.mark.skipif(not (shutil.which("make") and shutil.which("cc")), reason="no C toolchain")


@pytest.fixture(scope="module")
def cli(tmp_path_factory):
    build = tmp_path_factory.mktemp("cbuild")
    subprocess.run(["make", "-C", str(C_DIR), f"BUILD={build}", "cli"], check=True, capture_output=True)
    return str(build / "flame_cli")


def test_random_bursts(cli):
    rng = random.Random(7)
    cases, lines = [], []
    for _ in range(5000):
        n = rng.choice([0, *range(1, 33), 33])
        p = rng.choice([0.05, 0.3, 0.5, 0.8, 0.95])
        raw = [0 if rng.random() < p else rng.choice([1, 1, 7]) for _ in range(n)]
        cfg = Config(active_low=rng.random() < 0.5, vote_ratio=rng.choice([0.5, 0.625, 0.75, 1.0, 0.3]),
                     flicker_min=rng.choice([0, 0, 1, 2, 4]))
        cases.append((raw, cfg))
        lines.append(f"{int(cfg.active_low)} {cfg.vote_ratio!r} {cfg.flicker_min} {n} " + " ".join(map(str, raw)))
    out = subprocess.run([cli], input="\n".join(lines) + "\n", capture_output=True, text=True, check=True).stdout.splitlines()
    assert len(out) == len(cases)
    refused = 0
    for (raw, cfg), line in zip(cases, out):
        if not 1 <= len(raw) <= 32:
            assert line == "ERR"
            refused += 1
            continue
        r = process(raw, cfg)
        d, ratio, tr, n = line.split()
        assert (int(d), float(ratio), int(tr), int(n)) == (int(r.detected), r.ratio, r.transitions, r.n)
    assert refused > 50
