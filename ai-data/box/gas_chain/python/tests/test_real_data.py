"""Replay on real BME688 smoke. The sample (committed) is a regression guard; the full set checks the fiche criteria."""
import pathlib

import pytest

from gas_chain.data_mendeley import DEFAULT_DIR, load_all, load_sample
from gas_chain.evaluate import metrics, replay


def test_sample_strong_smoke_is_found_and_not_a_fault():
    d = load_sample()
    m = metrics(d, replay(d), start_phase=2)
    assert m["recall_strong"] >= 0.95
    assert m["fault_in_strong"] <= 0.01
    assert m["episodes_never_called"] == 0


def test_sample_false_smoke_is_the_known_slow_scan_case():
    """The sample holds node 3 profile 2 (77 s scans, ~10 clean scans): its power-on drift gives false smoke.
    Measured 4.0 % on the sample (RES-GAS-1). Guard against getting worse, not a pass level."""
    d = load_sample()
    assert metrics(d, replay(d))["false_smoke_clean"] <= 0.05


@pytest.mark.skipif(not pathlib.Path(DEFAULT_DIR).exists(), reason="full Mendeley set not on this machine")
def test_full_set_meets_fiche_criteria():
    d = load_all()
    res = replay(d)
    for burn in ("2021", "2025"):
        m = metrics(d, res, burn, start_phase=2)
        assert m["false_smoke_clean"] <= 0.02, burn
        assert m["recall_strong"] >= 0.95, burn
        assert m["fault_in_strong"] <= 0.01, burn
