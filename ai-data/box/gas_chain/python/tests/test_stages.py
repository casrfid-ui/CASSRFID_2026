"""Each stage of the gas chain tested alone, as a pure function. Numbers in comments are the default config."""
import dataclasses

import numpy as np
import pytest

from gas_chain import Config, DECOY, FAULT, F_RANGE, F_STUCK, NORMAL, SMOKE, stages

CFG = Config()
GOOD = np.full(10, 50_000.0)
T_OK, RH_OK = np.full(10, 25.0), np.full(10, 50.0)


# ---- stage 1: quality ------------------------------------------------------------------------
def flags(gas=GOOD, temp=T_OK, rh=RH_OK, prev=None, same=0):
    return stages.quality_flags(gas, temp, rh, prev, same, CFG)


def test_quality_accepts_a_normal_scan():
    assert flags()[0] == 0


@pytest.mark.parametrize("bad", [np.full(10, 999.0), np.full(10, 120_000_001.0)])
def test_quality_rejects_gas_out_of_range(bad):
    assert flags(gas=bad)[0] & F_RANGE


def test_quality_range_limits_are_inclusive_and_cover_saturation():
    assert flags(gas=np.full(10, 1_000.0))[0] == 0
    assert flags(gas=np.full(10, 102_400_000.0))[0] == 0     # BME688 saturation: valid reading


@pytest.mark.parametrize("temp,rh", [(np.full(10, -41.0), RH_OK), (np.full(10, 86.0), RH_OK), (T_OK, np.full(10, -1.0)), (T_OK, np.full(10, 100.5))])
def test_quality_rejects_temperature_or_humidity_out_of_range(temp, rh):
    assert flags(temp=temp, rh=rh)[0] & F_RANGE


def test_quality_one_bad_step_is_enough():
    gas = GOOD.copy()
    gas[7] = 10.0
    assert flags(gas=gas)[0] & F_RANGE


def test_quality_stuck_after_12_identical_scans():
    same, hits = 0, []
    for _ in range(14):
        f, same = stages.quality_flags(GOOD, T_OK, RH_OK, GOOD, same, CFG)
        hits.append(bool(f & F_STUCK))
    assert hits.index(True) == CFG.stuck_scans - 1 and all(hits[CFG.stuck_scans - 1:])


def test_quality_changing_scan_resets_the_stuck_count():
    f, same = stages.quality_flags(GOOD * 1.01, T_OK, RH_OK, GOOD, 11, CFG)
    assert same == 0 and not f & F_STUCK


def test_spike_flag_uses_the_median_of_seen_scans():
    window = np.zeros((5, 10))
    window[:3] = 8.0
    assert not stages.is_spike(np.full(10, 8.0 + 1.4), window, 3, CFG.spike_ln)
    assert stages.is_spike(np.full(10, 8.0 + 1.6), window, 3, CFG.spike_ln)
    assert not stages.is_spike(np.full(10, 99.0), window, 0, CFG.spike_ln)   # nothing seen yet


# ---- stage 2: compensation -------------------------------------------------------------------
def test_compensation_is_plain_ln_by_default():
    assert np.allclose(stages.compensate(GOOD, np.full(10, 40.0), np.full(10, 90.0), CFG), np.log(GOOD))


def test_compensation_formula():
    cfg = dataclasses.replace(CFG, a_t=0.02, b_h=-0.005)
    out = stages.compensate(GOOD, np.full(10, 35.0), np.full(10, 70.0), cfg)
    assert np.allclose(out, np.log(GOOD) - 0.02 * 10 - (-0.005) * 20)


# ---- stage 3: filter -------------------------------------------------------------------------
def test_median_rejects_a_lone_outlier_per_step():
    window = np.array([[1.0] * 10, [1.0] * 10, [9.0] * 10, [1.0] * 10, [1.0] * 10])
    assert np.allclose(stages.window_median(window, 5), 1.0)


def test_median_uses_only_the_scans_seen():
    window = np.zeros((5, 10))
    window[0], window[1] = 2.0, 4.0
    assert np.allclose(stages.window_median(window, 2), 3.0)


def test_smooth_first_value_starts_the_filter_and_is_a_copy():
    v = np.ones(10)
    out = stages.smooth(None, v, 0.35)
    out[0] = 5.0
    assert v[0] == 1.0


def test_smooth_moves_a_fraction_alpha_toward_the_new_value():
    assert np.allclose(stages.smooth(np.zeros(10), np.ones(10), 0.35), 0.35)


# ---- stage 4: baseline -----------------------------------------------------------------------
def test_learning_waits_for_burn_in_and_a_full_window():
    assert not stages.learning_gate(CFG.burnin_scans, 5, CFG)          # still in the burn-in
    assert not stages.learning_gate(CFG.burnin_scans + 1, 4, CFG)      # window not full
    assert stages.learning_gate(CFG.burnin_scans + 1, 5, CFG)


def test_baseline_follows_only_in_quiet_normal_air():
    assert stages.baseline_may_follow(NORMAL, 0.05, False, CFG)
    assert not stages.baseline_may_follow(NORMAL, 0.10, False, CFG)    # at the freeze score
    assert not stages.baseline_may_follow(SMOKE, 0.0, False, CFG)
    assert not stages.baseline_may_follow(NORMAL, 0.0, True, CFG)      # stuck sensor


def test_baseline_follow_time_constant():
    out = stages.baseline_follow(np.zeros(10), np.ones(10), CFG.tau_base_s, CFG.tau_base_s)
    assert np.allclose(out, 1 - np.exp(-1))
    assert np.allclose(stages.baseline_follow(np.zeros(10), np.ones(10), 0.0, CFG.tau_base_s), 0.0)


def test_baseline_follow_does_not_overshoot():
    out = stages.baseline_follow(np.zeros(10), np.ones(10), 1e9, CFG.tau_base_s)
    assert np.allclose(out, 1.0)


# ---- stage 5: depth per band -----------------------------------------------------------------
def test_band_depths_are_means_over_the_bands():
    depth = np.arange(10, dtype=float)
    assert np.allclose(stages.band_depths(depth, CFG.bands), [1.5, 5.0, 8.0])


# ---- stage 6: score --------------------------------------------------------------------------
@pytest.mark.parametrize("depth,score", [(-0.1, 0.0), (0.0, 0.0), (0.15, 0.5), (0.30, 1.0), (2.0, 1.0)])
def test_instant_score_is_clipped_linear(depth, score):
    assert stages.instant_score(depth, CFG.depth_full) == pytest.approx(score)


def test_cusum_accumulates_above_k_halves_below_and_is_capped():
    c = stages.update_cusum(0.0, 0.13, CFG)
    assert c == pytest.approx(0.10)
    assert stages.update_cusum(0.4, 0.01, CFG) == pytest.approx(0.2)
    assert stages.update_cusum(1.4, 5.0, CFG) == pytest.approx(1.5 * CFG.cusum_h)


def test_cusum_ignores_depth_equal_to_k():
    assert stages.update_cusum(0.4, CFG.cusum_k, CFG) == pytest.approx(0.2)


# ---- stage 7: class --------------------------------------------------------------------------
def want(score, depth=0.2, peak=5, current=NORMAL, cfg=CFG):
    return stages.wanted_class(score, depth, peak, current, cfg)


def test_class_thresholds_with_hysteresis():
    assert want(0.39) == NORMAL
    assert want(0.40) == SMOKE
    assert want(0.30, current=NORMAL) == NORMAL        # between off and on: not entered
    assert want(0.30, current=SMOKE) == SMOKE          # between off and on: kept
    assert want(0.19, current=SMOKE) == NORMAL         # below off: released


def test_class_cusum_only_score_keeps_current_state():
    assert want(0.6, depth=0.01, current=SMOKE) == SMOKE


def test_decoy_is_off_by_default_and_needs_an_early_peak_when_on():
    assert want(0.6, peak=0) == SMOKE
    on = dataclasses.replace(CFG, decoy_enabled=True)
    assert want(0.6, peak=1, cfg=on) == DECOY
    assert want(0.6, peak=6, cfg=on) == SMOKE


def run_debounce(wants, cls=NORMAL):
    cand, n, out = cls, 0, []
    for w in wants:
        cls, cand, n = stages.debounce(cls, cand, n, w, CFG)
        out.append(cls)
    return out


def test_debounce_needs_two_scans_for_smoke_and_three_to_release():
    assert run_debounce([SMOKE, SMOKE]) == [NORMAL, SMOKE]
    assert run_debounce([NORMAL] * 3, cls=SMOKE) == [SMOKE, SMOKE, NORMAL]


def test_debounce_fault_is_immediate():
    assert run_debounce([FAULT]) == [FAULT]


def test_debounce_interrupted_candidate_starts_again():
    assert run_debounce([SMOKE, NORMAL, SMOKE, SMOKE]) == [NORMAL, NORMAL, NORMAL, SMOKE]
    assert run_debounce([NORMAL, NORMAL, SMOKE, NORMAL, NORMAL, NORMAL], cls=SMOKE) == [SMOKE] * 5 + [NORMAL]
