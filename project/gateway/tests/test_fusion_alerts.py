from ffn_gateway.config import FusionParams
from ffn_gateway.fusion import Fusion
from ffn_gateway.ffp import frame as F


def test_prior_makes_a_difference():
    p = FusionParams()
    s = F.Status(gas_class=F.GAS_SMOKE, cam_valid=1, cam_label=F.CAM_FIRE, flame=0)
    r = {}
    for d in (1, 5):
        f = Fusion(p)
        f.observe_status(1, s, 0)
        r[d] = f.evaluate(1, d)
    assert r[5].statistic > r[1].statistic
    assert r[5].confirmed and not r[1].confirmed


def test_evidence_replaced_not_accumulated():
    f = Fusion(FusionParams())
    s = F.Status(gas_class=F.GAS_SMOKE)
    for _ in range(50):
        f.observe_status(1, s, 0)
    assert len([c for c in f.evaluate(0, 3).contributions if c[1] == "gas"]) == 1


def test_decay_and_hysteresis():
    f = Fusion(FusionParams())
    f.observe_status(1, F.Status(gas_class=F.GAS_SMOKE, flame=1), 0)
    f.observe_status(2, F.Status(gas_class=F.GAS_SMOKE, flame=1), 0)
    assert f.evaluate(1, 3).confirmed
    assert not f.evaluate(6000, 3).confirmed      # 100 min later: faded away


def test_warmup_and_fault_give_no_gas_evidence():
    f = Fusion(FusionParams())
    f.observe_status(1, F.Status(gas_class=F.GAS_SMOKE, warmup=1), 0)
    assert not any(c[1] == "gas" for c in f.evaluate(0, 3).contributions)


def test_vision_low_confidence_positive_is_ignored():
    f = Fusion(FusionParams())
    f.observe_vision(1, "fire", 0.3, 0)
    assert not f.evaluate(0, 3).contributions
    f.observe_vision(1, "fire", 0.9, 0)
    assert f.evaluate(0, 3).contributions[0][2] > 0
