"""Tuning constants of the gas chain. One frozen object, so a run is reproducible from its config."""
from dataclasses import dataclass

NSTEP = 10                       # heater temperatures per scan
NORMAL, SMOKE, DECOY, FAULT = 0, 1, 2, 3
CLASS_NAMES = ("normal", "smoke", "decoy", "sensor_fault")
F_RANGE, F_STUCK, F_SPIKE = 1, 2, 4   # fault bits; F_SPIKE is informational only


@dataclass(frozen=True)
class Config:
    # --- 2. quality check
    gas_min_ohm: float = 1_000.0
    gas_max_ohm: float = 120_000_000.0     # BME688 saturates at 102.4 Mohm: a valid reading (see RES-GAS-1)
    temp_min_c: float = -40.0
    temp_max_c: float = 85.0
    stuck_scans: int = 12                  # identical scans in a row = stuck sensor
    bad_scans_to_fault: int = 3            # consecutive out-of-range scans before the fault class
    spike_ln: float = 1.5                  # one scan this far from the window median is flagged (info only)
    # --- 3. filter
    median_window: int = 5
    ema_alpha: float = 0.35
    # --- 4. compensation
    t_offset_c: float = 0.0                # self-heating offset of the sensor temperature (calibrate on the box)
    a_t: float = 0.0                       # ln R per degC, fitted (RES-GAS-2)
    b_h: float = 0.0                       # ln R per % RH, fitted (RES-GAS-2)
    # --- 5. baseline
    burnin_scans: int = 6                  # scans ignored after power-on (sensor settling)
    warmup_scans: int = 6                  # scans averaged to build the first baseline
    tau_base_s: float = 6.0 * 3600.0       # baseline follows slow drift with this time constant
    freeze_score: float = 0.10             # baseline frozen at or above this score
    # --- 6. bands (step ranges, low / mid / high heater temperature)
    bands: tuple = ((0, 4), (4, 7), (7, 10))
    # --- 7. score and class
    depth_full: float = 0.30               # depth (ln units) that gives an instant score of 1
    cusum_k: float = 0.03
    cusum_h: float = 1.0
    smoke_on: float = 0.40
    smoke_off: float = 0.20
    on_scans: int = 2
    off_scans: int = 3
    decoy_enabled: bool = False            # no real decoy data: never reported unless enabled
    decoy_max_peak_step: int = 2
