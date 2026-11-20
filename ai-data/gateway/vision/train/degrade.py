"""OV2640-like degradations for training images (geometry is never changed, so YOLO labels stay valid).

Every operation is sampled from a seeded RNG. `severity` in [0, 1] scales all ranges.
THE RANGES ARE ASSUMPTIONS: no real OV2640 frame exists in the project yet. Calibrate them on real captures
(compare noise level, sharpness, colour cast and JPEG size of real frames with degraded D-Fire frames).
"""
import cv2
import numpy as np


def _blur(img, rng, s):
    sigma = rng.uniform(0.0, 1.6) * s
    return cv2.GaussianBlur(img, (0, 0), sigma) if sigma > 0.25 else img


def _lowres(img, rng, s):
    h, w = img.shape[:2]
    f = 1.0 - rng.uniform(0.0, 0.6) * s                     # keep 40..100 % of the linear resolution
    if f > 0.97:
        return img
    small = cv2.resize(img, (max(16, int(w * f)), max(16, int(h * f))), interpolation=cv2.INTER_AREA)
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)


def _colour(img, rng, s):
    x = img.astype(np.float32) / 255.0
    gain = 1.0 + rng.uniform(-0.15, 0.15, 3) * s            # white balance error per channel
    x = x * gain
    x = np.clip(x, 0, 1) ** (1.0 + rng.uniform(-0.25, 0.3) * s)     # gamma (exposure)
    c = 1.0 + rng.uniform(-0.25, 0.2) * s                    # contrast
    x = (x - 0.5) * c + 0.5 + rng.uniform(-0.08, 0.08) * s
    return (np.clip(x, 0, 1) * 255).astype(np.uint8)


def _noise(img, rng, s):
    sig = rng.uniform(0.0, 9.0) * s
    if sig < 0.5:
        return img
    x = img.astype(np.float32)
    shot = rng.normal(0, 1, x.shape).astype(np.float32) * np.sqrt(np.maximum(x, 1.0)) * (sig / 16.0)
    read = rng.normal(0, 1, x.shape).astype(np.float32) * sig * 0.5
    return np.clip(x + shot + read, 0, 255).astype(np.uint8)


def _vignette(img, rng, s):
    k = rng.uniform(0.0, 0.55) * s
    if k < 0.03:
        return img
    h, w = img.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    r2 = ((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2
    m = (1.0 - k * np.clip(r2 / 2.0, 0, 1))[..., None]
    return np.clip(img.astype(np.float32) * m, 0, 255).astype(np.uint8)


def _haze(img, rng, s):
    t = rng.uniform(0.0, 0.35) * s
    if t < 0.03:
        return img
    veil = np.array([205, 205, 210], np.float32) * rng.uniform(0.85, 1.05)
    return np.clip(img.astype(np.float32) * (1 - t) + veil * t, 0, 255).astype(np.uint8)


def _dirt(img, rng, s):
    n = int(rng.integers(0, 4)) if s > 0.3 else 0
    if n == 0:
        return img
    h, w = img.shape[:2]
    layer = np.zeros((h, w), np.float32)
    for _ in range(n):
        cv2.circle(layer, (int(rng.integers(0, w)), int(rng.integers(0, h))), int(rng.uniform(0.03, 0.12) * min(h, w)), 1.0, -1)
    layer = cv2.GaussianBlur(layer, (0, 0), 0.04 * min(h, w) + 1) * rng.uniform(0.15, 0.5) * s
    grey = np.array([120, 115, 105], np.float32)
    return np.clip(img.astype(np.float32) * (1 - layer[..., None]) + grey * layer[..., None], 0, 255).astype(np.uint8)


def _jpeg(img, rng, s):
    q = int(round(95 - rng.uniform(10, 70) * s))
    ok, buf = cv2.imencode(".jpg", img[..., ::-1], [cv2.IMWRITE_JPEG_QUALITY, max(q, 15)])
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)[..., ::-1].copy()


def flare(img, rng, strength=1.0):
    """Sun glare: bright warm core with a halo and a few ghost discs. Meant as a synthetic HARD NEGATIVE:
    use it only on images without fire (the label stays 'background')."""
    h, w = img.shape[:2]
    cx, cy = rng.uniform(0.1, 0.9) * w, rng.uniform(0.05, 0.5) * h
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / min(h, w)
    glow = np.exp(-(d / rng.uniform(0.04, 0.12)) ** 2) * strength
    halo = np.exp(-(d / rng.uniform(0.25, 0.5)) ** 2) * 0.35 * strength
    tint = np.array([1.0, rng.uniform(0.75, 0.95), rng.uniform(0.45, 0.8)], np.float32)
    add = (glow + halo)[..., None] * tint * 255
    out = img.astype(np.float32) + add
    for k in range(int(rng.integers(0, 4))):                 # ghosts along the axis to the image centre
        t = rng.uniform(0.3, 1.2)
        gx, gy = cx + (w / 2 - cx) * 2 * t * 0.5, cy + (h / 2 - cy) * 2 * t * 0.5
        dd = np.sqrt((xx - gx) ** 2 + (yy - gy) ** 2) / min(h, w)
        out += (np.exp(-(dd / rng.uniform(0.02, 0.06)) ** 2) * 0.35 * strength)[..., None] * tint * 255
    return np.clip(out, 0, 255).astype(np.uint8)


def night(img, rng):
    """Darkens a daytime scene to a night-like frame (synthetic NEGATIVE for background images only).
    Why: in D-Fire 62 % of the fire-only images are dark against 7 % of the background images, so a network can learn
    'dark = fire'. This adds dark images without fire. The colour cast and noise are assumptions, not a night model."""
    x = img.astype(np.float32) / 255.0
    x = (x ** rng.uniform(1.4, 2.2)) * rng.uniform(0.08, 0.35)
    x = x * np.array([0.85, 0.95, 1.1], np.float32)                      # slight blue cast
    x = x * 255.0 + rng.normal(0, rng.uniform(1.0, 4.0), x.shape)
    return np.clip(x, 0, 255).astype(np.uint8)


OPS = [("lowres", _lowres, 0.6), ("blur", _blur, 0.6), ("colour", _colour, 0.8), ("vignette", _vignette, 0.5),
       ("haze", _haze, 0.25), ("dirt", _dirt, 0.2), ("noise", _noise, 0.7), ("jpeg", _jpeg, 1.0)]


def degrade(img, rng, severity=0.6):
    """img: HxWx3 uint8 RGB. Returns (degraded image, names of the operations applied)."""
    out, used = img, []
    for name, fn, p in OPS:
        if rng.random() < p:
            new = fn(out, rng, severity)
            if new is not out:
                used.append(name)
            out = new
    return out, used
