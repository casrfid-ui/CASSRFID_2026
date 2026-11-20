"""Hourly FWI engine of the box. One call per hour; DMC and DC move once a day at local noon."""
from collections import deque
from dataclasses import dataclass, field

from . import codes
from .danger import danger_class, mode_for_class

NOON_HOUR = 12


@dataclass
class FwiState:
    ffmc: float = 85.0
    dmc: float = 6.0
    dc: float = 15.0
    rain_last_24h: deque = field(default_factory=lambda: deque(maxlen=24))


@dataclass
class FwiOutput:
    ffmc: float
    dmc: float
    dc: float
    isi: float
    bui: float
    fwi: float
    danger: int
    mode: str


class FwiEngine:
    """Feed one observation per hour (local time). Wind and rain are simulated in the prototype."""

    def __init__(self, le=codes.LE_46N, lf=codes.LF_46N, state=None):
        self.le, self.lf = le, lf
        self.state = state or FwiState()

    def update_hour(self, hour, month, temp_c, rh_pct, wind_kmh, rain_mm):
        """Advance one hour. Returns the indices valid at the end of this hour."""
        s = self.state
        s.rain_last_24h.append(rain_mm)
        s.ffmc = codes.ffmc_hourly(s.ffmc, temp_c, rh_pct, wind_kmh, rain_mm)
        if hour == NOON_HOUR:
            rain24 = sum(s.rain_last_24h)
            s.dmc = codes.dmc(s.dmc, temp_c, rh_pct, rain24, month, self.le)
            s.dc = codes.dc(s.dc, temp_c, rain24, month, self.lf)
        bui_value = codes.bui(s.dmc, s.dc)
        isi_value = codes.isi(s.ffmc, wind_kmh)
        fwi_value = codes.fwi(isi_value, bui_value)
        cls = danger_class(fwi_value)
        return FwiOutput(s.ffmc, s.dmc, s.dc, isi_value, bui_value, fwi_value, cls, mode_for_class(cls))
