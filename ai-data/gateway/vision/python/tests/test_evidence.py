import numpy as np
from gateway_vision.evidence import PlattCalibrator, ece, Sprt, run_scene


def synth(n, rng, a=3.0, b=-1.0):
    """Scores whose TRUE probability is sigmoid(a * logit(s) + b), but that a raw reader would trust as-is."""
    s = rng.beta(0.6, 0.6, n)
    z = a * np.log(s / (1 - s)) + b
    y = rng.random(n) < 1 / (1 + np.exp(-z))
    return s, y


def test_platt_recovers_parameters_and_reduces_ece():
    rng = np.random.default_rng(0)
    s, y = synth(40000, rng)
    cal = PlattCalibrator().fit(s, y)
    assert abs(cal.a - 3.0) < 0.15 and abs(cal.b + 1.0) < 0.15
    s2, y2 = synth(20000, rng)
    assert ece(cal.predict(s2), y2) < 0.02 < ece(s2, y2)       # raw scores are badly calibrated, calibrated ones are not


def test_llr_sign_and_prior_free():
    rng = np.random.default_rng(1)
    s, y = synth(20000, rng)
    cal = PlattCalibrator().fit(s, y)
    l = cal.llr(np.array([0.02, 0.5, 0.98]))
    assert l[0] < 0 < l[2] and l[0] < l[1] < l[2]


def gauss_llr(x, mu=1.0):                     # N(mu,1) vs N(0,1): LLR = mu*x - mu^2/2
    return mu * x - mu * mu / 2


def test_wald_bounds_hold_for_independent_frames():
    rng = np.random.default_rng(2)
    alpha, beta = 0.01, 0.1
    fa = miss = 0; N = 4000; used = []
    for _ in range(N):
        d, n = run_scene(gauss_llr(rng.normal(0, 1, 200)), alpha=alpha, beta=beta, floor=-1e9); fa += d == "alarm"
        d, n = run_scene(gauss_llr(rng.normal(1, 1, 200)), alpha=alpha, beta=beta, floor=-1e9); miss += d == "clear"; used.append(n)
    assert fa / N <= alpha * 1.5 and miss / N <= beta * 1.3            # Wald's bounds (with sampling slack)
    assert np.mean(used) < 20                                          # a few frames, not hundreds


def test_correlated_frames_break_the_bound_and_damping_only_reduces_it():
    """Frames of the same scene share a bias (a red roof misread in every photo). The undamped test then raises far
    more false alarms than alpha, and damping helps but does NOT restore alpha: persistent errors are the problem,
    not noise. Measured here: about 24 % without damping, 11 % with rho = 0.15, for alpha = 1 %."""
    rng = np.random.default_rng(3)
    alpha = 0.01
    def scene(n=60, shared=0.8):
        bias = rng.normal(0, 1)                          # per-scene bias common to all frames
        return gauss_llr(shared * bias + np.sqrt(1 - shared ** 2) * rng.normal(0, 1, n))
    N = 3000
    raw = np.mean([run_scene(scene(), alpha=alpha, beta=0.1, floor=-1e9)[0] == "alarm" for _ in range(N)])
    damp = np.mean([run_scene(scene(), alpha=alpha, beta=0.1, floor=-1e9, rho=0.15)[0] == "alarm" for _ in range(N)])
    assert raw > 10 * alpha                              # the independence assumption fails badly
    assert damp < 0.6 * raw and damp > 3 * alpha         # damping reduces, does not fix


def test_floor_keeps_a_late_fire_detectable():
    quiet = np.full(500, -1.0); fire = np.full(30, 1.5)
    d_floor, _ = run_scene(np.r_[quiet, fire], alpha=0.001, beta=0.1, floor=-2.0)
    assert d_floor == "alarm"
    d_nofloor, _ = run_scene(np.r_[quiet, fire], alpha=0.001, beta=0.1, floor=-1e9)
    assert d_nofloor == "clear"                          # stopped long before the fire; a floor + reset is needed in service
