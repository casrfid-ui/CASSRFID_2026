import os, sys, csv, subprocess, tempfile
from pathlib import Path
import numpy as np
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from degrade import degrade, flare, night  # noqa: E402
sys.path.insert(0, str(HERE.parents[2] / "box" / "camera" / "python" / "src"))
from box_camera import quality  # noqa: E402


def scene(seed=0, h=360, w=640):
    r = np.random.default_rng(seed)
    base = np.zeros((h, w, 3), np.float32)
    base[:] = [90, 130, 70]
    for _ in range(60):
        x, y = int(r.integers(0, w - 40)), int(r.integers(0, h - 40))
        base[y:y + int(r.integers(10, 40)), x:x + int(r.integers(10, 40))] = r.integers(30, 220, 3)
    return np.clip(base + r.normal(0, 4, base.shape), 0, 255).astype(np.uint8)


def sharp(img):
    g = img.astype(np.float32).mean(2)
    return float(np.abs(np.diff(g, axis=1)).mean() + np.abs(np.diff(g, axis=0)).mean())


def test_shape_dtype_and_determinism():
    img = scene()
    a, ua = degrade(img, np.random.default_rng(5), 0.6)
    b, ub = degrade(img, np.random.default_rng(5), 0.6)
    assert a.shape == img.shape and a.dtype == np.uint8 and np.array_equal(a, b) and ua == ub
    c, _ = degrade(img, np.random.default_rng(6), 0.6)
    assert not np.array_equal(a, c)


def test_severity_scales_the_change_and_softens():
    img = scene(1)
    ch, sh = [], []
    for s in (0.0, 0.3, 0.6, 1.0):
        d = [degrade(img, np.random.default_rng(i), s)[0] for i in range(40)]
        ch.append(np.mean([np.abs(x.astype(int) - img).mean() for x in d])); sh.append(np.mean([sharp(x) for x in d]))
    assert ch[0] < ch[1] < ch[2] < ch[3]            # more severity, bigger change
    assert sh[3] < sh[0]                             # and softer on average (blur, low resolution, JPEG)


def test_degraded_images_mostly_pass_the_box_quality_check():
    """The simulator must produce frames the box would still send; extremes may be refused."""
    img = scene(2)
    flagged = 0
    for i in range(60):
        d, _ = degrade(img, np.random.default_rng(100 + i), 0.6)
        g = d.mean(2)[::4, ::4]
        flagged += quality(g.astype(np.uint8)).flags != 0
    assert flagged <= 6


def test_flare_brightens_only_a_region_and_keeps_shape():
    img = scene(3)
    f = flare(img, np.random.default_rng(1), 1.0)
    assert f.shape == img.shape and (f.astype(int) - img).mean() > 0 and (f.astype(int) - img).min() >= 0


DATA = HERE.parents[2] / "data" / "fire detection"
CSV = HERE.parents[2] / "data" / "vision_split" / "split_v2.csv"


@pytest.mark.skipif(not (DATA.exists() and CSV.exists()), reason="D-Fire data not present")
def test_lists_and_degraded_set_on_real_files(tmp_path):
    out = tmp_path / "lists"
    subprocess.run([sys.executable, str(HERE / "make_lists.py"), str(DATA), str(CSV), str(out)], check=True, capture_output=True)
    counts = {s: len((out / f"{s}.txt").read_text().splitlines()) for s in ("train", "val", "test")}
    assert counts == {"train": 15068, "val": 3230, "test": 3229}
    first = (out / "val.txt").read_text().splitlines()[0]   # absolute path (may contain spaces)
    assert (DATA / first).exists() and (DATA / first.replace("/images/", "/labels/").rsplit(".", 1)[0]).with_suffix(".txt").exists()
    y = (out / "data_v2.yaml").read_text()
    assert "0: smoke" in y and "1: fire" in y
    deg = tmp_path / "deg"
    subprocess.run([sys.executable, str(HERE / "build_degraded.py"), str(DATA), str(CSV), str(deg), "--limit", "12"], check=True, capture_output=True)
    imgs = sorted((deg / "images").glob("*.jpg")); labs = sorted((deg / "labels").glob("*.txt"))
    assert len(imgs) == 12 and [p.stem for p in imgs] == [p.stem for p in labs]


def test_night_is_dark_and_keeps_shape():
    img = scene(4)
    n = night(img, np.random.default_rng(2))
    assert n.shape == img.shape and n.mean() < 0.4 * img.mean() and n.mean() > 1.0
