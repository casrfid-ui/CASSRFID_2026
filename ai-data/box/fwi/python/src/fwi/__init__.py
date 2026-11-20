"""Box FWI engine: Canadian Forest Fire Weather Index, daily codes plus hourly FFMC, and the mapping to mode."""
from .codes import bui, dc, dmc, ffmc_daily, ffmc_hourly, fwi, isi
from .engine import FwiEngine, FwiState
from .danger import CLASS_NAMES, MODE_ALERT, MODE_ECO, danger_class, mode_for_class

__all__ = ["bui", "dc", "dmc", "ffmc_daily", "ffmc_hourly", "fwi", "isi", "FwiEngine", "FwiState",
           "CLASS_NAMES", "MODE_ALERT", "MODE_ECO", "danger_class", "mode_for_class"]
