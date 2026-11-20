"""Alert levels L1..L5 and the decision of when to dispatch.

L1 high risk      FWI danger class >= high on at least one fresh box
L2 suspicion      a box is in Suspicion, or fusion posterior above p_suspect
L3 fire           a box reports FIRE (hard rule, never overruled) or fusion confirmed; latched until an operator acknowledges
                  AND no box is in FIRE any more
L4 box lost       heartbeat missing beyond lost_after_factor x heartbeat period, or a last-gasp frame
L5 maintenance    battery_low, housing_hot, supply_fault, gas fault, camera fault, unsynced clock (after 1 h), weak link

`top` orders by severity: 3, 4, 2, 5, 1 (L4 numerically above L3 but less urgent than a fire).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .ffp import frame as F

SEVERITY = {3: 5, 4: 4, 2: 3, 5: 2, 1: 1, 0: 0}
NAMES = {0: "none", 1: "L1 high risk", 2: "L2 suspicion", 3: "L3 fire", 4: "L4 box lost", 5: "L5 maintenance"}
HIGH_DANGER = 4


@dataclass
class Alert:
    level: int
    box: int          # 0 = system wide
    reason: str

    def to_dict(self):
        return {"level": self.level, "name": NAMES[self.level], "box": self.box, "reason": self.reason}


@dataclass
class Assessment:
    alerts: list = field(default_factory=list)
    top: int = 0
    fire_boxes: list = field(default_factory=list)
    fire_reason: str = ""

    def levels_for(self, box: int):
        return sorted({a.level for a in self.alerts if a.box in (box, 0)})

    def to_dict(self):
        return {"top": self.top, "top_name": NAMES[self.top], "alerts": [a.to_dict() for a in self.alerts], "fire_boxes": self.fire_boxes}


def reasons_text(r: int) -> str:
    parts = [n for bit, n in ((F.R_GAS, "gas"), (F.R_FLAME, "flame"), (F.R_CAMERA, "camera"), (F.R_FWI, "fwi")) if r & bit]
    return "+".join(parts) or "none"


class AlertEngine:
    def __init__(self, cfg, store):
        self.cfg = cfg
        self.store = store
        self.fire_latched = False
        self.fire_boxes: set[int] = set()
        self.acked_at: float = 0.0
        self.operator_ack = False
        self.last = Assessment()
        self.started = 0.0

    def acknowledge(self, now: float):
        self.operator_ack = True
        self.acked_at = now

    def evaluate(self, now: float, registry, fusion_result) -> Assessment:
        cfg = self.cfg
        if not self.started:
            self.started = now
        out: list[Alert] = []
        lost_after = cfg.lost_after_factor * cfg.heartbeat_s
        fire_now = {}
        for b in registry.boxes.values():
            if not b.last_seen:
                continue
            s = b.last_status
            age = now - b.last_seen
            if b.last_gasp:
                out.append(Alert(4, b.id, "last-gasp frame (supply or heat fault)"))
                b.lost = True
            elif age > lost_after:
                out.append(Alert(4, b.id, f"no frame for {int(age)} s"))
                b.lost = True
            else:
                b.lost = False
            if s is None:
                continue
            if s.state == F.STATE_FIRE and not b.lost:
                fire_now[b.id] = f"box FIRE ({reasons_text(s.reasons)})"
            elif s.state == F.STATE_FIRE and b.last_gasp:
                fire_now[b.id] = "last gasp while in FIRE"
            if s.state == F.STATE_SUSPICION:
                out.append(Alert(2, b.id, f"box suspicion ({reasons_text(s.reasons)})"))
            if s.danger >= HIGH_DANGER and age <= lost_after and not s.provisional:
                out.append(Alert(1, b.id, f"FWI {s.fwi:.1f} danger class {s.danger}"))
            m = []
            if s.flags & F.SF_BATTERY_LOW: m.append("battery low")
            if s.flags & F.SF_HOUSING_HOT: m.append("housing hot")
            if s.flags & F.SF_SUPPLY_FAULT: m.append("supply fault")
            if s.gas_faults: m.append(f"gas fault {s.gas_faults}")
            if s.cam_status != 0: m.append(f"camera status {s.cam_status}")
            if s.flags & F.SF_STORAGE_ERROR: m.append("storage error")
            if (s.flags & F.SF_CLOCK_UNSYNCED) and now - self.started > 3600: m.append("clock unsynced")
            if s.mode == F.MODE_SURVIVAL: m.append("survival mode")
            if b.rssi and (b.rssi < cfg.weak_rssi_dbm or b.snr < cfg.weak_snr_db): m.append(f"weak link rssi {b.rssi} snr {b.snr:.0f}")
            if m:
                out.append(Alert(5, b.id, ", ".join(m)))

        fusion_fire = fusion_result is not None and fusion_result.confirmed
        if fusion_fire:
            out.append(Alert(2, 0, f"fusion S={fusion_result.statistic:.1f} (posterior {fusion_result.posterior:.3f})"))
        elif fusion_result is not None and fusion_result.suspected:
            out.append(Alert(2, 0, f"fusion posterior {fusion_result.posterior:.3f}"))

        # L3: box decision (hard rule) or fusion confirmation, latched
        if fire_now or fusion_fire:
            if not self.fire_latched:
                self.operator_ack = False
            self.fire_latched = True
            self.fire_boxes |= set(fire_now)
        if self.fire_latched and self.operator_ack and not fire_now and not fusion_fire:
            self.fire_latched = False
            self.fire_boxes.clear()
        reason = ""
        if self.fire_latched:
            reason = "; ".join(f"box {k}: {v}" for k, v in fire_now.items()) or ("fusion confirmed" if fusion_fire else "latched, waiting for operator acknowledgement")
            for bx in sorted(self.fire_boxes or {0}):
                out.append(Alert(3, bx, reason))

        top = 0
        for a in out:
            if SEVERITY[a.level] > SEVERITY[top]:
                top = a.level
        self.last = Assessment(out, top, sorted(self.fire_boxes), reason)
        return self.last
