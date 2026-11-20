"""Tuning constants of the flame processing. One frozen object, so a run is reproducible from its config."""
from dataclasses import dataclass

MAX_SAMPLES = 32                 # longest burst accepted (fixed buffers in the C port)


@dataclass(frozen=True)
class Config:
    active_low: bool = True          # KY-026 pulls DO low on flame (to check on the module)
    burst_samples: int = 8           # reads per wake-up taken by the firmware (information for the firmware)
    vote_ratio: float = 0.625        # share of positive reads that makes the burst positive (5 of 8)
    flicker_min: int = 0             # minimum transitions for a positive burst; 0 = rule off (unvalidated)
