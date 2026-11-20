"""Commands to the boxes. They reach a box only when it transmits: the bridge queues them and delivers after the next ack,
or immediately for a box known to be listening (Suspicion/Fire). Threshold policy values are ASSUMED (config.ThresholdPolicy)."""
from __future__ import annotations

from . import uart_link as U
from .ffp import frame as F


class Downlink:
    def __init__(self, cfg, store, link=None):
        self.cfg, self.store, self.link = cfg, store, link
        self.seq = 0
        self.sent: list = []

    def _send(self, box, cmd_id, args, immediate, why, now):
        self.seq = (self.seq + 1) & 0xFF
        wire = F.make(F.T_CMD, self.cfg.gateway_id, box, self.seq, F.Cmd(cmd_id, tuple(args))).encode()
        if self.link:
            self.link.send(U.tx_frame(wire, immediate))
        self.sent.append((now, box, cmd_id, tuple(args)))
        self.store.add_event("cmd", f"cmd {cmd_id} -> box {box}: {why}", box=box,
                             data={"cmd": cmd_id, "args": list(args), "immediate": immediate}, t=now)
        return wire

    def set_thresholds(self, box, smoke_on, smoke_off, cam_conf, now, why="threshold policy"):
        q = lambda v: max(0, min(255, int(round(v * 100))))
        return self._send(box, F.C_SET_THRESH, (q(smoke_on), q(smoke_off), q(cam_conf), 0, 0, 0), False, why, now)

    def risk_prior(self, box, value, now):
        return self._send(box, F.C_RISK_PRIOR, (max(0, min(255, int(round(value * 255)))), 0, 0, 0, 0, 0), False, "risk prior", now)

    def force_alert(self, box, now, why="neighbour alert"):
        return self._send(box, F.C_FORCE_MODE, (F.MODE_ALERT, 0, 0, 0, 0, 0), True, why, now)

    def reset_fire(self, box, now):
        return self._send(box, F.C_RESET_FIRE, (0,) * 6, True, "operator reset", now)

    def sim_weather(self, box, enable, wind_kmh, rain_x10, now):
        return self._send(box, F.C_SIM_WX, (1 if enable else 0, int(wind_kmh) & 0xFF, int(rain_x10) & 0xFF, 0, 0, 0), False, "simulated weather", now)

    def ping(self, box, now):
        return self._send(box, F.C_PING, (0,) * 6, False, "ping", now)

    def apply_threshold_policy(self, registry, now):
        pol = self.cfg.thresholds
        if not pol.enabled:
            return
        for b in registry.boxes.values():
            s = b.last_status
            if not s or s.provisional:
                continue
            cls = 2 if s.danger >= pol.danger_high_from else (0 if s.danger <= pol.danger_low_to else 1)
            if cls != b.thresholds_class or now - b.thresholds_sent_t > pol.resend_s:
                self.set_thresholds(b.id, pol.smoke_on[cls], pol.smoke_off[cls], pol.camera_conf[cls], now, f"danger class {s.danger}")
                b.thresholds_class, b.thresholds_sent_t = cls, now

    def neighbours_to_alert(self, registry, lost_box, now):
        for b in registry.boxes.values():
            if b.id != lost_box and b.last_status and not b.lost and b.last_status.mode == F.MODE_ECO:
                self.force_alert(b.id, now, f"box {lost_box} lost")
