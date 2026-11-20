import sys
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from overlay import mask_overlay, paste_overlay, LABEL_DET as LABEL, DATE_DET as DATE  # noqa: E402
from overlay_probe import present  # noqa: E402


def scene(h=720, w=1280, seed=0):
    r = np.random.default_rng(seed)
    return np.clip(r.normal(110, 25, (h, w, 3)), 30, 190).astype(np.uint8)       # mid-grey: no black box, no white text


def gray(x):
    return x.mean(2)


def test_paste_creates_a_detectable_overlay_and_mask_removes_it():
    img = scene()
    assert not present(gray(img), LABEL) and not present(gray(img), DATE)
    p = paste_overlay(img, np.random.default_rng(1))
    assert present(gray(p), LABEL) and present(gray(p), DATE)
    m = mask_overlay(p)
    assert not present(gray(m), LABEL) and not present(gray(m), DATE)


def test_mask_only_touches_the_regions_and_keeps_shape():
    img = scene(seed=2)
    m = mask_overlay(img)
    assert m.shape == img.shape and m.dtype == np.uint8
    diff = np.abs(m.astype(int) - img).sum(2) > 0
    h, w = img.shape[:2]
    assert diff[int(0.2 * h):int(0.8 * h)].sum() == 0                      # nothing in the middle band
    assert diff.mean() < 0.06


def test_works_at_other_resolutions():
    for h, w in ((360, 640), (480, 640), (180, 320)):
        img = scene(h, w)
        p = paste_overlay(img, np.random.default_rng(3))
        assert p.shape == img.shape and not np.array_equal(p, img)
        assert mask_overlay(p).shape == img.shape


def test_paste_is_independent_of_the_input_and_seeded():
    img = scene(seed=4)
    a = paste_overlay(img, np.random.default_rng(7)); b = paste_overlay(img, np.random.default_rng(7))
    assert np.array_equal(a, b) and np.array_equal(img, scene(seed=4))
