"""Turns raw gateway JSON (integers of the 16-byte frame protocol) into the names the UI shows."""
from __future__ import annotations

STATE = {0: "normal", 1: "suspicion", 2: "fire"}
MODE = {0: "eco", 1: "alert", 2: "survival"}
GAS = {0: "normal", 1: "smoke", 2: "decoy", 3: "fault"}
CAM = {0: "background", 1: "fire", 2: "smoke"}
# EFFIS fire danger classes, as computed on the box (fwi_danger_class): edges 5.2 / 11.2 / 21.3 / 38 / 50
DANGER = {0: "very low", 1: "low", 2: "moderate", 3: "high", 4: "very high", 5: "extreme"}
REASONS = ((1, "gas"), (2, "flame"), (4, "camera"), (8, "fwi"))
FLAGS = ((1, "battery_low"), (2, "housing_hot"), (4, "supply_fault"), (8, "clock_unsynced"), (16, "storage_error"),
         (32, "gps_on"), (64, "pump"), (128, "camera_on"))
LEVEL_NAMES = {0: "none", 1: "L1 high risk", 2: "L2 suspicion", 3: "L3 fire", 4: "L4 box lost", 5: "L5 maintenance"}


def bits(v: int, table) -> list[str]:
    return [n for b, n in table if (v or 0) & b]


def box_view(b: dict, levels: list[int], heartbeat_s: float = 600.0) -> dict:
    s = b.get("status") or {}
    w = b.get("weather") or {}
    flags = bits(s.get("flags", 0), FLAGS)
    gas_cls = GAS.get(s.get("gas_class"), "unknown") if s else "unknown"
    cam_ok = s.get("cam_status", 0) == 0 if s else None      # camera off (not woken) is normal, not a fault
    age = b.get("age_s")
    online = age is not None and not b.get("lost") and age <= 2.5 * heartbeat_s
    out = {
        "id": b["id"], "name": b.get("name") or f"Box {b['id']}", "lat": b.get("lat", 0.0), "lon": b.get("lon", 0.0),
        "pos_source": b.get("pos_source", "survey"), "online": online, "age_s": age, "lost": bool(b.get("lost")),
        "last_gasp": bool(b.get("last_gasp")), "rssi": b.get("rssi"), "snr": b.get("snr"), "frames": b.get("frames", 0), "relayed": bool(b.get("relayed")),
        "weather_simulated": bool(b.get("weather_simulated")), "levels": sorted(set(levels)),
        "has_status": bool(s),
    }
    if s:
        out.update({
            "state": STATE.get(s["state"], "unknown"), "mode": MODE.get(s["mode"], "unknown"),
            "reasons": bits(s.get("reasons", 0), REASONS),
            "gas": {"score": s.get("gas_score"), "class": gas_cls, "bands": s.get("bands", [])},
            "flame": bool(s.get("flame")),
            "camera": {"label": CAM.get(s.get("cam_label"), "unknown"), "valid": bool(s.get("cam_valid")), "conf": s.get("cam_conf")},
            "fwi": {"value": s.get("fwi"), "danger": s.get("danger"), "danger_name": DANGER.get(s.get("danger"), "unknown"),
                    "provisional": bool(s.get("provisional"))},
            "battery_pct": s.get("battery_pct"), "flags": flags,
        })
    out["health"] = {
        "gas": "fault" if gas_cls == "fault" else ("ok" if s else "unknown"),
        "flame": "ok" if s else "unknown",
        "camera": ("ok" if cam_ok else "fault") if s else "unknown",
        "battery": "low" if "battery_low" in flags else ("ok" if s else "unknown"),
        "housing": "hot" if "housing_hot" in flags else ("ok" if s else "unknown"),
        "supply": "fault" if "supply_fault" in flags else ("ok" if s else "unknown"),
        "link": "weak" if (b.get("rssi") or 0) < -115 and b.get("rssi") else ("ok" if online else "down"),
    }
    if w:
        out["weather"] = {"temp_c": w.get("temp_c"), "rh": w.get("rh"), "wind_kmh": w.get("wind_kmh"), "rain_mm": w.get("rain_mm"),
                          "codes": {k: w.get(k) for k in ("ffmc", "dmc", "dc", "isi", "bui")}, "provisional": bool(w.get("provisional"))}
    if b.get("vision"):
        out["vision"] = b["vision"]
    return out


def sample_of(bv: dict) -> dict:
    w = bv.get("weather") or {}
    return {"gas": (bv.get("gas") or {}).get("score"), "fwi": (bv.get("fwi") or {}).get("value"),
            "danger": (bv.get("fwi") or {}).get("danger"), "battery": bv.get("battery_pct"), "rssi": bv.get("rssi"),
            "snr": bv.get("snr"), "temp": w.get("temp_c"), "rh": w.get("rh"), "wind": w.get("wind_kmh"), "rain": w.get("rain_mm"),
            "state": {"normal": 0, "suspicion": 1, "fire": 2}.get(bv.get("state"), None)}
