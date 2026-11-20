"""Flame processing of one wake-up."""
from dataclasses import dataclass

from . import stages
from .config import MAX_SAMPLES, Config


@dataclass
class FlameResult:
    detected: bool
    ratio: float
    transitions: int
    n: int


def process(raw, cfg=None):
    """raw: the digital reads of the burst (0 / 1). Raises ValueError for an empty or too long burst."""
    cfg = cfg or Config()
    n = len(raw)
    if n < 1 or n > MAX_SAMPLES:
        raise ValueError(f"burst length must be 1..{MAX_SAMPLES}, got {n}")
    active = stages.polarity(raw, cfg.active_low)
    flicker = stages.transitions(active)
    detected = stages.vote(active, cfg.vote_ratio) and flicker >= cfg.flicker_min
    return FlameResult(detected, sum(active) / n, flicker, n)
