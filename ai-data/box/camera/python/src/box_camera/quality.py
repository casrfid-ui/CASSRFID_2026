"""Image quality of a small grayscale frame: dark, blocked, saturated, blurry. Reference of cam_quality()."""
from dataclasses import dataclass
import numpy as np

DARK, BLOCKED, SATURATED, BLURRY = 1, 2, 4, 8


@dataclass
class QualityConfig:
    min_mean: float = 15.0
    min_std: float = 4.0
    max_sat_frac: float = 0.5
    min_grad: float = 1.0


@dataclass
class Quality:
    mean: float
    std: float
    sat_frac: float
    dark_frac: float
    grad: float
    flags: int


def quality(frame, cfg: QualityConfig = QualityConfig()) -> Quality:
    a = np.asarray(frame)
    if a.ndim != 2 or a.shape[0] < 2 or a.shape[1] < 2 or a.size > 19200:
        raise ValueError("frame must be 2-D, at least 2x2 and at most 19200 pixels")
    a = a.astype(np.int64)
    n = a.size
    mean = a.sum() / n
    var = max((a * a).sum() / n - mean * mean, 0.0)
    std = float(np.sqrt(var))
    gsum = np.abs(np.diff(a, axis=1)).sum() + np.abs(np.diff(a, axis=0)).sum()
    npairs = a.shape[0] * (a.shape[1] - 1) + a.shape[1] * (a.shape[0] - 1)
    grad = gsum / npairs
    sat = float((a >= 250).sum() / n)
    dark = float((a <= 5).sum() / n)
    flags = 0
    if mean < cfg.min_mean: flags |= DARK
    if std < cfg.min_std: flags |= BLOCKED
    if sat > cfg.max_sat_frac: flags |= SATURATED
    if grad < cfg.min_grad and std >= cfg.min_std: flags |= BLURRY
    return Quality(float(mean), std, sat, dark, float(grad), flags)
