"""C and Python give the same quality numbers and the same protocol decisions."""
import subprocess, subprocess as sp
from pathlib import Path
import numpy as np
import pytest
from box_camera import QualityConfig, quality, parse_response, build_headers, ProtocolError
from box_camera.protocol import build_response, build_error

C_DIR = Path(__file__).resolve().parents[2] / "c"
CLI = C_DIR / "build" / "cam_cli"


@pytest.fixture(scope="module")
def cli():
    sp.run(["make", "-C", str(C_DIR), "cli"], check=True, capture_output=True)
    return CLI


def run(cli, lines):
    return subprocess.run([str(cli)], input="\n".join(lines) + "\n", capture_output=True, text=True, check=True).stdout.strip().split("\n")


def frames(rng):
    out = []
    for _ in range(60):
        h, w = int(rng.integers(2, 120)), int(rng.integers(2, 160))
        kind = int(rng.integers(0, 5))
        if kind == 0: f = rng.integers(0, 256, (h, w))
        elif kind == 1: f = np.full((h, w), int(rng.integers(0, 256)))
        elif kind == 2: f = rng.integers(0, 8, (h, w))
        elif kind == 3: f = np.clip(rng.normal(245, 8, (h, w)), 0, 255).astype(int)
        else: f = (np.add.outer(np.arange(h), np.arange(w)) * rng.uniform(0.1, 3)).astype(int) % 256
        out.append(f.astype(np.uint8))
    return out


def test_quality_parity(cli):
    rng = np.random.default_rng(1)
    cfg = QualityConfig()
    fr = frames(rng)
    lines = [f"Q {f.shape[1]} {f.shape[0]} {cfg.min_mean} {cfg.min_std} {cfg.max_sat_frac} {cfg.min_grad} " + " ".join(map(str, f.ravel())) for f in fr]
    for f, out in zip(fr, run(cli, lines)):
        v = out.split(); q = quality(f, cfg)
        assert np.allclose([float(x) for x in v[:5]], [q.mean, q.std, q.sat_frac, q.dark_frac, q.grad], rtol=0, atol=1e-9)
        assert int(v[5]) == q.flags


def test_protocol_parity(cli):
    bodies = [
        build_response(7, "fire", 0.934, 210), build_response(7, "smoke", 1.0), build_response(7, "background", 0.0, 5),
        build_response(8, "fire", 0.5), build_error(7, "decode"),
        '{"v":2,"id":7,"label":"fire","conf":0.9}', '{"id":7,"label":"fire","conf":0.9}',
        '{"v":1,"id":7,"label":"cat","conf":0.9}', '{"v":1,"id":7,"label":"fire","conf":1.5}',
        '{"v":1,"id":7,"label":"fire","conf":-0.2}', '{"v":1,"id":7,"label":"fire"}', 'nonsense', '{"v":1,"id":7,"label":"fire',
    ]
    outs = run(cli, [f"P 7 {b}" for b in bodies])
    for b, out in zip(bodies, outs):
        rc, lab, conf, ms = out.split()
        try:
            l, c, m = parse_response(b, 7); assert (int(rc), int(lab), float(conf), int(ms)) == (0, l, c, m), b
        except ProtocolError as e:
            assert int(rc) == e.args[0], b


def test_headers_parity(cli):
    out = run(cli, ["H 3 7 1700000000 5"])
    txt = "\n".join(out)
    assert txt == (build_headers(3, 7, 1700000000, 5) + "END").replace("\r\n", "\r\n").strip("\n") or txt.replace("\r", "") == (build_headers(3, 7, 1700000000, 5) + "END").replace("\r", "").strip()
