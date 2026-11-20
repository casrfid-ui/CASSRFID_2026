"""Drone mission for a confirmed fire. SIMULATED: the mission is written as JSON (MAVLink mission items, ids as in the MAVLink
common message set) and, if `drone.connection` is set and pymavlink is installed, a connection is checked. No flight is started."""
from __future__ import annotations

import json
import time
from pathlib import Path

CMD_TAKEOFF, CMD_WAYPOINT, CMD_DO_SET_SERVO, CMD_RTL = 22, 16, 183, 20


def build_mission(cfg, target_lat, target_lon, alert_id: str) -> dict:
    d = cfg.drone
    alt = d.altitude_m
    items = [
        {"seq": 0, "command": CMD_TAKEOFF, "name": "TAKEOFF", "lat": d.base_lat, "lon": d.base_lon, "alt": alt},
        {"seq": 1, "command": CMD_WAYPOINT, "name": "WAYPOINT_FIRE", "lat": target_lat, "lon": target_lon, "alt": alt},
        {"seq": 2, "command": CMD_DO_SET_SERVO, "name": "RELEASE", "servo": d.release_servo, "pwm": d.release_pwm},
        {"seq": 3, "command": CMD_RTL, "name": "RTL"},
    ]
    return {"id": alert_id, "simulated": True, "created": time.time(), "target": {"lat": target_lat, "lon": target_lon},
            "base": {"lat": d.base_lat, "lon": d.base_lon}, "items": items,
            "note": "Simulated mission: written to disk, never armed or started by this software."}


def dispatch(cfg, mission: dict) -> dict:
    d = cfg.drone
    Path(d.missions_dir).mkdir(parents=True, exist_ok=True)
    path = Path(d.missions_dir) / f"mission_{mission['id']}.json"
    path.write_text(json.dumps(mission, indent=2))
    result = {"file": str(path), "uploaded": False}
    if d.connection:
        try:
            from pymavlink import mavutil  # type: ignore
            m = mavutil.mavlink_connection(d.connection)
            m.wait_heartbeat(timeout=5)
            result["connected"] = True      # the upload sequence is left to the integration with the real autopilot
        except Exception as e:             # pragma: no cover
            result["error"] = str(e)
    return result
