"""Danger class (European EFFIS thresholds) and the mode it sets on the box."""
CLASS_NAMES = ("very_low", "low", "moderate", "high", "very_high", "extreme")
THRESHOLDS = (5.2, 11.2, 21.3, 38.0, 50.0)
MODE_ECO, MODE_ALERT = "eco", "alert"
ALERT_FROM_CLASS = 3                       # high or above: Alert mode (spec table 7.2, L1)


def danger_class(fwi_value):
    """Index 0..5 from the FWI."""
    return sum(fwi_value >= t for t in THRESHOLDS)


def mode_for_class(cls):
    """Eco below `high`, Alert from `high`. Survival (low battery) is decided elsewhere."""
    return MODE_ALERT if cls >= ALERT_FROM_CLASS else MODE_ECO
