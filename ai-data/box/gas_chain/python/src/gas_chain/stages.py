"""The stages of the gas chain as small pure functions. The state lives in `chain.GasChain`."""
import numpy as np

from .config import DECOY, FAULT, F_RANGE, F_STUCK, NORMAL, SMOKE


def quality_flags(gas, temp_c, rh, prev_gas, same_count, cfg):
    """Stage 2. Returns (fault bits, new count of identical scans). Range faults make the scan bad."""
    faults = 0
    out_of_range = (
        not (np.isfinite(gas).all() and np.isfinite(temp_c).all() and np.isfinite(rh).all())   # NaN fails every comparison
        or (gas < cfg.gas_min_ohm).any() or (gas > cfg.gas_max_ohm).any()
        or (temp_c < cfg.temp_min_c).any() or (temp_c > cfg.temp_max_c).any()
        or (rh < 0).any() or (rh > 100).any()
    )
    if out_of_range:
        faults |= F_RANGE
    identical = prev_gas is not None and bool(np.array_equal(gas, prev_gas))
    same_count = same_count + 1 if identical else 0
    if same_count >= cfg.stuck_scans:
        faults |= F_STUCK
    return faults, same_count


def compensate(gas, temp_c, rh, cfg):
    """Stage 4. ln of the gas resistance with the linear temperature and humidity effect removed."""
    t = temp_c - cfg.t_offset_c
    return np.log(gas) - cfg.a_t * (t - 25.0) - cfg.b_h * (rh - 50.0)


def is_spike(x, window, filled, spike_ln):
    """Stage 2 (informational). True if one step is further than `spike_ln` from the median of the scans seen so far."""
    return bool(filled) and bool(np.abs(x - window_median(window, filled)).max() > spike_ln)


def window_median(window, filled):
    """Stage 3a. Median per heater step over the scans seen so far (at most the window size)."""
    return np.median(window[:filled], axis=0)


def smooth(previous, value, alpha):
    """Stage 3b. Exponential smoothing; the first value starts the filter."""
    if previous is None:
        return value.copy()
    return previous + alpha * (value - previous)


def learning_gate(scans, filled, cfg):
    """Stage 5a. True when this scan counts toward the first baseline: burn-in over and median window full."""
    return scans > cfg.burnin_scans and filled >= cfg.median_window


def baseline_may_follow(cls, score, stuck, cfg):
    """Stage 5b. The baseline follows slow drift only in quiet normal air; any doubt freezes it."""
    return cls == NORMAL and score < cfg.freeze_score and not stuck


def baseline_follow(base, ema, dt_s, tau_s):
    """Stage 5c. First-order follow of the filtered signal, time constant `tau_s`, step `dt_s`."""
    beta = 1.0 - np.exp(-float(dt_s) / tau_s)
    return base + beta * (ema - base)


def band_depths(depth, bands):
    """Stage 6. Mean depth per band (low, mid, high heater temperature)."""
    return np.array([depth[a:b].mean() for a, b in bands])


def instant_score(depth_max, depth_full):
    """Stage 7a. Depth mapped to 0..1."""
    return float(min(max(depth_max / depth_full, 0.0), 1.0))


def update_cusum(cusum, depth_max, cfg):
    """Stage 7b. CUSUM accumulates depth above k, halves when quiet, capped at 1.5 h."""
    if depth_max > cfg.cusum_k:
        cusum += depth_max - cfg.cusum_k
    else:
        cusum *= 0.5
    return min(cusum, 1.5 * cfg.cusum_h)


def wanted_class(score, depth_max, peak_step, current, cfg):
    """Stage 7c. Class wanted by the thresholds, before debounce. Hysteresis keeps smoke between off and on."""
    if score >= cfg.smoke_on:
        if depth_max < 0.04 and current in (SMOKE, DECOY):
            return current
        if cfg.decoy_enabled and peak_step <= cfg.decoy_max_peak_step:
            return DECOY
        return SMOKE
    if score >= cfg.smoke_off and current in (SMOKE, DECOY):
        return current
    return NORMAL


def debounce(cls, cand, cand_n, want, cfg):
    """Stage 7d. A new class must be wanted for several scans in a row (one for a fault).
    Returns the new (class, candidate, candidate count)."""
    if want == cls:
        return cls, want, 0
    cand_n = cand_n + 1 if want == cand else 1
    need = 1 if want == FAULT else (cfg.off_scans if want == NORMAL else cfg.on_scans)
    if cand_n >= need:
        return want, want, 0
    return cls, want, cand_n
