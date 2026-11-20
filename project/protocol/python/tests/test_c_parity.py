"""The Python codec and the C codec must agree on every vector produced by the C test."""
import pathlib
import subprocess
import sys

import pytest

HERE = pathlib.Path(__file__).resolve()
C_DIR = HERE.parents[2] / "c"
sys.path.insert(0, str(HERE.parents[1]))

import ffp  # noqa: E402


@pytest.fixture(scope="module")
def built():
    r = subprocess.run(["make", "-C", str(C_DIR), "test"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return C_DIR / "build"


def c_decode(build, hexs):
    out = subprocess.run([str(build / "ffp_cli"), "decode", hexs], capture_output=True, text=True).stdout.strip()
    return dict(kv.split("=") for kv in out.split())


def test_vectors_roundtrip_and_match_c(built):
    lines = (built / "vectors.txt").read_text().split("\n")
    n = 0
    for ln in filter(None, lines):
        kind, hx = ln.split()
        raw = bytes.fromhex(hx)
        f = ffp.decode(raw)
        assert f.encode() == raw                      # re-encoding gives the same bytes
        body = ffp.body_of(f)
        assert body.pack() == f.payload or kind in ("cmd", "ack", "time")   # padded types are checked below
        if kind == "status":
            c = c_decode(built, hx)
            for k, v in c.items():
                if k in ("type", "flags", "origin", "dest", "seq"):
                    assert int(v) == getattr(f, k), k
                elif k.startswith("b") and k[1:].isdigit():
                    assert int(v) == body.band[int(k[1:])], k
                elif k == "sflags":
                    assert int(v) == body.flags, k
                else:
                    assert int(v) == getattr(body, k), k
        n += 1
    assert n >= 45


def test_python_frames_decode_in_c(built):
    st = ffp.Status(state=2, mode=1, reasons=7, gas_score=200, gas_class=1, gas_faults=5, warmup=0, flame=1, scan_bad=1, cam_label=2, cam_valid=1,
                    cam_status=7, cam_conf=180, flags=0xA5, fwi_x2=99, danger=4, fwi_updated=1, provisional=1, repeat=2, battery_pct=63, band=(1, 2, 3))
    fr = ffp.make(ffp.T_ALERT, 3, 0, 250, st, flags=ffp.F_ACK_REQ | ffp.F_SIM_WX)
    c = c_decode(built, fr.encode().hex())
    assert int(c["origin"]) == 3 and int(c["seq"]) == 250 and int(c["flags"]) == 5
    expect = dict(state=2, mode=1, reasons=7, gas_score=200, gas_class=1, gas_faults=5, flame=1, scan_bad=1, cam_label=2, cam_valid=1, cam_status=7,
                  cam_conf=180, sflags=0xA5, fwi_x2=99, danger=4, fwi_updated=1, provisional=1, repeat=2, battery_pct=63, b0=1, b1=2, b2=3)
    for k, v in expect.items():
        assert int(c[k]) == v, k


def test_rejections_match_c(built):
    good = ffp.make(ffp.T_HEARTBEAT, 1, 0, 1, ffp.Status()).encode()
    bad = bytearray(good)
    bad[4] ^= 1
    with pytest.raises(ffp.FrameError) as e:
        ffp.decode(bytes(bad))
    assert e.value.code == -2 and c_decode(built, bytes(bad).hex())["error"] == "-2"
    with pytest.raises(ffp.FrameError) as e:
        ffp.decode(good[:15])
    assert e.value.code == -1
