"""Latest known state of every box, built from the frames the bridge forwards."""
from __future__ import annotations

from dataclasses import dataclass, field

from . import ffp  # noqa: F401  (path set up in __init__ of ffp shim)
from .ffp import frame as F


@dataclass
class BoxState:
    id: int
    name: str = ""
    lat: float = 0.0
    lon: float = 0.0
    pos_source: str = "survey"           # survey | gps
    last_seen: float = 0.0
    last_status: F.Status | None = None
    last_status_t: float = 0.0
    last_telem: F.Telem | None = None
    last_telem_t: float = 0.0
    last_type: int = 0
    rssi: int = 0
    snr: float = 0.0
    frames: int = 0
    lost: bool = False
    last_gasp: bool = False
    last_gasp_t: float = 0.0
    sim_wx: bool = False
    vision: dict | None = None           # last gateway re-check of a camera frame
    thresholds_sent_t: float = 0.0
    thresholds_class: int = -1
    relayed: bool = False                # last frame arrived through the neighbour box (mesh relay)

    def to_dict(self, now: float) -> dict:
        s = self.last_status
        d = {"id": self.id, "name": self.name, "lat": self.lat, "lon": self.lon, "pos_source": self.pos_source,
             "age_s": round(now - self.last_seen, 1) if self.last_seen else None, "rssi": self.rssi, "snr": self.snr,
             "frames": self.frames, "relayed": self.relayed, "lost": self.lost, "last_gasp": self.last_gasp, "weather_simulated": self.sim_wx}
        if s:
            d["status"] = {"state": s.state, "mode": s.mode, "reasons": s.reasons, "gas_score": round(s.score, 3), "gas_class": s.gas_class,
                           "flame": s.flame, "cam_label": s.cam_label, "cam_valid": s.cam_valid, "cam_status": s.cam_status, "cam_conf": round(s.cam_confidence, 3),
                           "fwi": s.fwi, "danger": s.danger, "battery_pct": s.battery_pct, "flags": s.flags,
                           "bands": [round(x, 3) for x in s.bands], "provisional": bool(s.provisional)}
        if self.last_telem:
            t = self.last_telem
            d["weather"] = {"temp_c": t.temp, "rh": t.rh, "wind_kmh": t.wind_kmh, "rain_mm": t.rain_mm, "ffmc": t.ffmc, "dmc": t.dmc,
                            "dc": t.dc, "isi": t.isi, "bui": t.bui, "provisional": bool(t.provisional)}
        if self.vision:
            d["vision"] = self.vision
        return d


class Registry:
    def __init__(self, cfg):
        self.cfg = cfg
        self.boxes: dict[int, BoxState] = {}
        for b in cfg.boxes:
            self.boxes[b.id] = BoxState(b.id, b.name, b.lat, b.lon)

    def get(self, box_id: int) -> BoxState:
        if box_id not in self.boxes:
            site = self.cfg.box(box_id)
            self.boxes[box_id] = BoxState(box_id, site.name, site.lat, site.lon)
        return self.boxes[box_id]

    def update(self, frame: F.Frame, rssi: int, snr: float, now: float):
        b = self.get(frame.origin)
        b.last_seen, b.last_type, b.rssi, b.snr = now, frame.type, rssi, snr
        b.frames += 1
        b.lost = False
        b.relayed = bool(frame.flags & F.F_RELAYED)
        if frame.simulated_wx:
            b.sim_wx = True
        body = F.body_of(frame)
        if frame.type in (F.T_ALERT, F.T_STATE, F.T_HEARTBEAT, F.T_LAST_GASP):
            b.last_status, b.last_status_t = body, now
            if frame.type == F.T_LAST_GASP:
                b.last_gasp, b.last_gasp_t = True, now
            elif b.last_gasp and now - b.last_gasp_t > 1:
                b.last_gasp = False           # it came back
        elif frame.type == F.T_TELEM:
            b.last_telem, b.last_telem_t = body, now
        elif frame.type == F.T_POS and body.fix:
            b.lat, b.lon, b.pos_source = body.lat, body.lon, "gps"
        return b

    def fresh_boxes(self, now: float, max_age_s: float):
        return [b for b in self.boxes.values() if b.last_seen and now - b.last_seen <= max_age_s]
