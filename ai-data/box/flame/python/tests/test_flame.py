import pytest

from flame import Config, process
from flame.synthetic import clean_burst, flame_burst, steady_burst
import random


def test_active_low_zero_is_flame():
    r = process([0] * 8)
    assert r.detected and r.ratio == 1.0 and r.transitions == 0 and r.n == 8


def test_active_low_ones_are_dark():
    r = process([1] * 8)
    assert not r.detected and r.ratio == 0.0


def test_active_high_polarity_inverts():
    cfg = Config(active_low=False)
    assert process([1] * 8, cfg).detected
    assert not process([0] * 8, cfg).detected


def test_vote_limit_is_five_of_eight():
    four = [0] * 4 + [1] * 4
    five = [0] * 5 + [1] * 3
    assert not process(four).detected
    assert process(five).detected


def test_vote_is_scaled_to_the_burst_length():
    assert process([0, 0, 1]).detected is True          # 2 of 3 = 0.667 >= 0.625
    assert process([0, 1, 1]).detected is False         # 1 of 3
    assert process([0]).detected is True and process([1]).detected is False


def test_a_lone_glitch_is_rejected():
    for k in range(8):
        raw = [1] * 8
        raw[k] = 0
        assert not process(raw).detected


def test_transitions_counted_and_flicker_rule_off_by_default():
    raw = [0, 1, 0, 1, 0, 0, 0, 0]
    assert process(raw).transitions == 4
    assert process([0] * 8).detected                    # steady is accepted when the rule is off


def test_flicker_rule_when_enabled_rejects_a_steady_burst():
    cfg = Config(flicker_min=2)
    assert not process([0] * 8, cfg).detected
    assert process([0, 0, 1, 0, 0, 1, 0, 0], cfg).detected


@pytest.mark.parametrize("raw", [[], [0] * 33])
def test_bad_length_raises(raw):
    with pytest.raises(ValueError):
        process(raw)


def test_nonzero_values_count_as_one():
    assert not process([2, 5, 255, 1, 1, 1, 1, 1]).detected


def test_synthetic_models_behave_as_described():
    rng = random.Random(0)
    assert process(steady_burst(8)).detected
    det = sum(process(flame_burst(8, rng)).detected for _ in range(2000)) / 2000
    assert 0.7 < det < 0.95                                  # model: a flickering flame is detected in about 8 bursts of 10
    fa = sum(process(clean_burst(8, 0.05, rng)).detected for _ in range(20000)) / 20000
    assert fa < 0.001                                    # 5 % glitches almost never pass the vote
