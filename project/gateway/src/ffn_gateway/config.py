"""Configuration of the gateway application. One JSON file; every field has a default so a bare `{}` runs a simulation."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path


@dataclass
class BoxSite:
    id: int
    name: str = ""
    lat: float = 0.0          # surveyed position, used until the box reports a GPS fix
    lon: float = 0.0


@dataclass
class FusionParams:
    """Assumed sensor characteristics (true-positive / false-positive rates per witness). NOT measured: placeholders to be
    replaced by values from the controlled recordings. See FICHE.md, section Fusion."""
    gas_smoke_tpr: float = 0.85
    gas_smoke_fpr: float = 0.03
    gas_decoy_tpr: float = 0.10
    gas_decoy_fpr: float = 0.30
    flame_tpr: float = 0.60
    flame_fpr: float = 0.02
    camera_tpr: float = 0.85
    camera_fpr: float = 0.02
    vision_tpr: float = 0.85       # gateway re-check
    vision_fpr: float = 0.03
    # prior probability of a fire in the zone over the evidence time constant, by FWI danger class 0..5
    prior_by_danger: tuple = (0.0005, 0.001, 0.002, 0.005, 0.010, 0.020)
    decay_s: float = 900.0         # evidence fades back to the prior with this time constant
    alpha: float = 0.05            # SPRT false-alarm rate
    beta: float = 0.05             # SPRT miss rate
    p_suspect: float = 0.30


@dataclass
class ThresholdPolicy:
    """Thresholds pushed to the boxes (bounded again on the box). Values are assumptions, not tuned."""
    enabled: bool = True
    danger_high_from: int = 4
    danger_low_to: int = 1
    smoke_on: tuple = (0.45, 0.40, 0.35)       # low risk, default, high risk
    smoke_off: tuple = (0.22, 0.20, 0.18)
    camera_conf: tuple = (0.65, 0.60, 0.55)
    resend_s: float = 6 * 3600.0


@dataclass
class DroneConfig:
    enabled: bool = True
    connection: str = ""                       # e.g. "udpout:127.0.0.1:14550"; empty = write the mission file only (simulated)
    base_lat: float = 0.0
    base_lon: float = 0.0
    altitude_m: float = 40.0
    release_servo: int = 7
    release_pwm: int = 1900
    missions_dir: str = "missions"


@dataclass
class GatewayConfig:
    gateway_id: int = 8
    db_path: str = "gateway.db"
    serial_port: str = ""                      # "" = no bridge (tests / simulation); e.g. "/dev/ttyAMA0"
    serial_baud: int = 115200
    ai_data_root: str = ""                     # path of the repository's ai-data folder ("" = look next to this project)
    models: dict = field(default_factory=lambda: {
        "risk_gru": "gateway/risk_gru/models/risk_gru_demo_synthetic.npz",
        "fwi_forecast": "gateway/fwi_forecast/models/fwi_climate_synthetic.json",
        "gas_trend": "gateway/gas_trend/models/gas_trend_demo.npz",
        "autoencoder": "",                     # phase B slot
        "gas_classifier": "",                  # phase B slot
    })
    boxes: list = field(default_factory=lambda: [BoxSite(1, "box-1"), BoxSite(2, "box-2")])
    phone_numbers: list = field(default_factory=list)       # international form, e.g. "+216..."
    emails: list = field(default_factory=list)
    dashboard_url: str = ""                    # base URL of the dashboard backend ("" = none)
    dashboard_token: str = ""
    dashboard_push_s: float = 0.0              # > 0: push the status snapshot to the dashboard every N s and run the
                                               # operator commands it returns (works behind a mobile NAT); 0 = off
    api_host: str = "127.0.0.1"
    api_port: int = 8090
    api_token: str = ""
    heartbeat_s: float = 600.0
    lost_after_factor: float = 2.5
    slow_path_period_s: float = 300.0
    dedupe_window_s: float = 180.0
    origin_lat: float = 0.0                    # local metric frame of the spread models (0,0 = first box)
    origin_lon: float = 0.0
    sim_wind_to_deg: float = 90.0              # wind direction: not measured, simulated (flagged)
    weak_rssi_dbm: float = -115.0
    weak_snr_db: float = -15.0
    fusion: FusionParams = field(default_factory=FusionParams)
    thresholds: ThresholdPolicy = field(default_factory=ThresholdPolicy)
    drone: DroneConfig = field(default_factory=DroneConfig)
    utc_offset_min: int = 60

    def box(self, box_id: int) -> BoxSite:
        for b in self.boxes:
            if b.id == box_id:
                return b
        return BoxSite(box_id, f"box-{box_id}")


def _build(cls, data):
    kw = {}
    for f in fields(cls):
        if f.name not in data:
            continue
        v = data[f.name]
        if f.name == "boxes":
            v = [BoxSite(**b) if isinstance(b, dict) else b for b in v]
        elif f.name in ("fusion", "thresholds", "drone") and isinstance(v, dict):
            sub = {"fusion": FusionParams, "thresholds": ThresholdPolicy, "drone": DroneConfig}[f.name]
            v = _build(sub, v)
        elif isinstance(f.default, tuple) and isinstance(v, list):
            v = tuple(v)
        elif f.name == "models":
            base = f.default_factory()
            base.update(v)
            v = base
        kw[f.name] = v
    return cls(**kw)


def load_config(path: str | None = None, overrides: dict | None = None) -> GatewayConfig:
    data = {}
    if path:
        data = json.loads(Path(path).read_text())
    if overrides:
        data.update(overrides)
    return _build(GatewayConfig, data)
