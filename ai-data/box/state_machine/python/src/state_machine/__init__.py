"""Box state machine: Normal -> Suspicion -> Fire."""
from .machine import (FIRE, NORMAL, SUSPICION, STATE_NAMES, Config, Inputs, Output, StateMachine,
                      R_CAMERA, R_FLAME, R_FWI, R_GAS)

__all__ = ["StateMachine", "Config", "Inputs", "Output", "NORMAL", "SUSPICION", "FIRE", "STATE_NAMES",
           "R_GAS", "R_FLAME", "R_CAMERA", "R_FWI"]
