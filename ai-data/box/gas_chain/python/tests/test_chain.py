import numpy as np

from gas_chain import (F_RANGE, F_SPIKE, F_STUCK, FAULT, NORMAL, SMOKE, Config, GasChain, NSTEP)


def run(chain, sensor, n, **kw):
    return [chain.update(*sensor.scan(**kw), 30) for _ in range(n)]


def test_clean_air_stays_normal(sensor):
    chain = GasChain()
    out = run(chain, sensor, 300)
    assert not out[-1].warmup
    assert all(r.cls == NORMAL for r in out)
    assert max(r.score for r in out[40:]) < 0.2


def test_warmup_reports_no_class_change(sensor):
    chain = GasChain()
    out = run(chain, sensor, 10)
    assert all(r.warmup for r in out)
    assert all(r.cls == NORMAL for r in out)


def test_step_drop_is_smoke_then_recovers(ready_chain, sensor):
    smoke = run(ready_chain, sensor, 20, drop=1.0)
    first = next(i for i, r in enumerate(smoke) if r.cls == SMOKE)
    assert first <= 6, "smoke must be called within a few scans of a 1 ln drop"
    after = run(ready_chain, sensor, 40)
    assert after[-1].cls == NORMAL


def test_lone_spike_is_not_smoke(ready_chain, sensor):
    res = ready_chain.update(*sensor.scan(drop=3.0), 30)
    assert res.faults & F_SPIKE
    after = run(ready_chain, sensor, 10)
    assert res.cls != SMOKE and all(r.cls == NORMAL for r in after)


def test_out_of_range_scan_is_skipped_then_fault(ready_chain, sensor):
    gas, t, h = sensor.scan()
    gas[3] = 10.0
    r1 = ready_chain.update(gas, t, h, 30)
    assert r1.scan_bad and r1.faults & F_RANGE and r1.cls == NORMAL
    ready_chain.update(gas, t, h, 30)
    r3 = ready_chain.update(gas, t, h, 30)
    assert r3.cls == FAULT
    assert ready_chain.update(*sensor.scan(), 30).scan_bad is False


def test_saturated_reading_is_valid(ready_chain, sensor):
    gas, t, h = sensor.scan()
    gas[9] = 102_400_000.0
    assert not ready_chain.update(gas, t, h, 30).scan_bad


def test_stuck_sensor_becomes_fault(ready_chain, sensor):
    gas, t, h = sensor.scan()
    last = None
    for _ in range(Config().stuck_scans + 2):
        last = ready_chain.update(gas, t, h, 30)
    assert last.faults & F_STUCK and last.cls == FAULT


def test_baseline_frozen_during_smoke_and_follows_drift_when_quiet(sensor):
    chain = GasChain()
    run(chain, sensor, 40)
    base0 = chain.snapshot()
    run(chain, sensor, 400, drop=1.0)             # long smoke
    assert np.allclose(chain.snapshot(), base0, atol=0.05), "baseline must not follow the smoke"
    run(chain, sensor, 40)                         # smoke ends
    assert chain.cls == NORMAL
    for _ in range(4000):                          # clean air drifts down 0.00003 ln per scan (0.0036 ln/h at 30 s scans)
        sensor.base_ln = sensor.base_ln - 0.00003
        res = chain.update(*sensor.scan(), 30)
        assert res.cls == NORMAL, "a slow drift must not be called smoke"
    assert (chain.snapshot() - base0).mean() < -0.08, "baseline must follow slow drift"


def test_bands_localise_the_response(ready_chain, sensor):
    drop = np.zeros(NSTEP)
    drop[7:] = 1.0
    out = run(ready_chain, sensor, 15, drop=drop)
    low, mid, high = out[-1].bands
    assert high > 0.5 and abs(low) < 0.2 and abs(mid) < 0.2


def test_compensation_removes_temperature_effect(sensor):
    cfg = Config(a_t=-0.02)
    chain = GasChain(cfg)
    run(chain, sensor, 40)
    # +10 degC lowers every ln R by 0.2 (a_t = -0.02 per degC): compensated, no smoke
    hot = []
    for _ in range(30):
        gas, t, h = sensor.scan(drop=0.2, temp=35.0)
        hot.append(chain.update(gas, t, h, 30))
    assert all(r.cls == NORMAL for r in hot)


def test_restore_skips_warmup(ready_chain, sensor):
    saved = ready_chain.snapshot()
    fresh = GasChain()
    fresh.restore(saved)
    for _ in range(Config().median_window):
        fresh.update(*sensor.scan(), 30)
    assert not fresh.update(*sensor.scan(), 30).warmup


def test_decoy_never_reported_by_default(ready_chain, sensor):
    drop = np.zeros(NSTEP)
    drop[:2] = 1.5                                 # peak at the first steps
    out = run(ready_chain, sensor, 15, drop=drop)
    assert all(r.cls != 2 for r in out)


def test_inputs_are_not_modified(ready_chain, sensor):
    gas, t, h = sensor.scan()
    g0, t0, h0 = gas.copy(), t.copy(), h.copy()
    ready_chain.update(gas, t, h, 30)
    assert (gas == g0).all() and (t == t0).all() and (h == h0).all()


def test_same_input_same_output(sensor):
    a, b = GasChain(), GasChain()
    s1, s2 = type(sensor)(seed=3), type(sensor)(seed=3)
    ra = [a.update(*s1.scan(), 30).score for _ in range(60)]
    rb = [b.update(*s2.scan(), 30).score for _ in range(60)]
    assert ra == rb


def test_drift_faster_than_k_over_tau_is_called_smoke(sensor):
    """Design limit (RES-GAS-4): a drift above cusum_k / tau_base (0.005 ln/h) outruns the baseline."""
    chain = GasChain()
    run(chain, sensor, 40)
    called = False
    for _ in range(4000):                          # 0.012 ln/h at 30 s scans
        sensor.base_ln = sensor.base_ln - 0.0001
        called |= chain.update(*sensor.scan(), 30).cls == SMOKE
    assert called
