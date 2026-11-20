"""Box gas chain (BME680): scan -> quality -> filter -> compensation -> baseline -> bands -> score + class."""
from .chain import GasChain, GasResult
from .config import (CLASS_NAMES, DECOY, F_RANGE, F_SPIKE, F_STUCK, FAULT, NORMAL, NSTEP, SMOKE, Config)

__all__ = ["GasChain", "GasResult", "Config", "NORMAL", "SMOKE", "DECOY", "FAULT", "CLASS_NAMES",
           "F_RANGE", "F_STUCK", "F_SPIKE", "NSTEP"]
