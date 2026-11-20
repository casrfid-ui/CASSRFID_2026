"""Stateful gas chain: one scan in, one result out. Pure Python + numpy, no I/O.

Order of the spec (figure 2): scan -> quality -> filter -> T/RH compensation -> baseline -> bands -> score + class.
Compensation runs before the filter here so that the filter works on the quantity the baseline is built on."""
from dataclasses import dataclass, field

import numpy as np

from . import stages
from .config import CLASS_NAMES, F_RANGE, F_SPIKE, F_STUCK, FAULT, NORMAL, NSTEP, Config


@dataclass
class GasResult:
    score: float = 0.0
    cls: int = NORMAL
    faults: int = 0
    warmup: bool = True
    scan_bad: bool = False
    depth: float = 0.0
    peak_step: int = 0
    bands: np.ndarray = field(default_factory=lambda: np.zeros(3))

    @property
    def cls_name(self):
        return CLASS_NAMES[self.cls]

    def score_u8(self):
        """Score on one byte, as it would travel in the frame."""
        return int(round(255 * self.score))


class GasChain:
    """One instance per sensor. Call `update` for every scan."""

    def __init__(self, cfg=None):
        self.cfg = cfg or Config()
        self.scans = 0
        self.prev_gas = None
        self.same_count = 0
        self.bad_count = 0
        self.window = np.zeros((self.cfg.median_window, NSTEP))
        self.window_pos = 0
        self.window_filled = 0
        self.ema = None
        self.base = None
        self.warm_sum = np.zeros(NSTEP)
        self.warm_n = 0
        self.cusum = 0.0
        self.cls = NORMAL
        self.cand, self.cand_n = NORMAL, 0

    # ---- baseline persistence (flash) -----------------------------------------------------------
    def snapshot(self):
        """Baseline to save in flash. None while it is not ready."""
        return None if self.base is None else self.base.copy()

    def restore(self, base):
        """Start from a saved baseline: no burn-in and no warm-up (fix for the power-on drift, RES-GAS-4)."""
        self.base = np.asarray(base, float).copy()
        self.warm_n = self.cfg.warmup_scans

    # ---- one scan -------------------------------------------------------------------------------
    def update(self, gas, temp_c, rh, dt_s):
        """gas in ohm, temp_c in degC, rh in %, dt_s in seconds. Returns a GasResult."""
        cfg = self.cfg
        gas = np.asarray(gas, float)
        temp_c = np.asarray(temp_c, float)
        rh = np.asarray(rh, float)
        res = GasResult()

        faults, self.same_count = stages.quality_flags(gas, temp_c, rh, self.prev_gas, self.same_count, cfg)
        self.prev_gas = gas.copy()

        if faults & F_RANGE:
            return self._bad_scan(res, faults)
        self.bad_count = 0
        self.scans += 1

        x = stages.compensate(gas, temp_c, rh, cfg)
        if stages.is_spike(x, self.window, self.window_filled, cfg.spike_ln):
            faults |= F_SPIKE
        self.window[self.window_pos] = x
        self.window_pos = (self.window_pos + 1) % cfg.median_window
        self.window_filled = min(self.window_filled + 1, cfg.median_window)
        med = stages.window_median(self.window, self.window_filled)
        self.ema = stages.smooth(self.ema, med, cfg.ema_alpha)

        if self.base is None or self.warm_n < cfg.warmup_scans:
            self._learn_baseline()
            res.faults = faults
            res.cls = FAULT if faults & F_STUCK else self.cls
            return res

        depth = self.base - self.ema                        # resistance drops in smoke: depth > 0
        bands = stages.band_depths(depth, cfg.bands)
        depth_max = max(0.0, float(bands.max()))
        self.cusum = stages.update_cusum(self.cusum, depth_max, cfg)
        inst = stages.instant_score(depth_max, cfg.depth_full)
        cum = float(min(max(self.cusum / cfg.cusum_h, 0.0), 1.0))
        score = max(inst, cum)
        peak = int(np.argmax(depth))

        want = FAULT if faults & F_STUCK else stages.wanted_class(score, depth_max, peak, self.cls, cfg)
        self._debounce(want)

        if stages.baseline_may_follow(self.cls, score, bool(faults & F_STUCK), cfg):
            self.base = stages.baseline_follow(self.base, self.ema, dt_s, cfg.tau_base_s)

        res.score, res.cls, res.faults, res.warmup = score, self.cls, faults, False
        res.depth, res.peak_step, res.bands = depth_max, peak, bands
        return res

    # ---- internals ------------------------------------------------------------------------------
    def _learn_baseline(self):
        """Average the filtered signal over the warm-up scans, after the burn-in."""
        cfg = self.cfg
        if not stages.learning_gate(self.scans, self.window_filled, cfg):
            return
        self.warm_sum += self.ema
        self.warm_n += 1
        if self.warm_n == cfg.warmup_scans:
            self.base = self.warm_sum / self.warm_n

    def _bad_scan(self, res, faults):
        """A bad scan never enters the state. Several in a row make the fault class."""
        self.bad_count += 1
        res.scan_bad, res.faults, res.warmup = True, faults, self.base is None
        if self.bad_count >= self.cfg.bad_scans_to_fault:
            self.cls = FAULT
        res.cls = self.cls
        return res

    def _debounce(self, want):
        self.cls, self.cand, self.cand_n = stages.debounce(self.cls, self.cand, self.cand_n, want, self.cfg)
