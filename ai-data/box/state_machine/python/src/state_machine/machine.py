"""State machine of the box. Pure Python, no I/O: one `step` per wake-up."""
from dataclasses import dataclass, field

NORMAL, SUSPICION, FIRE = 0, 1, 2
STATE_NAMES = ("normal", "suspicion", "fire")
R_GAS, R_FLAME, R_CAMERA, R_FWI = 1, 2, 4, 8          # reason-code bits carried by every alert


@dataclass(frozen=True)
class Config:
    eco_interval_s: float = 300.0
    alert_interval_s: float = 30.0
    survival_interval_s: float = 3600.0
    suspicion_interval_s: float = 30.0
    flame_reads_to_trigger: int = 2
    clear_scans: int = 10
    camera_confidence: float = 0.6
    camera_min_period_s: float = 30.0
    alert_repeats: int = 3
    fire_hold_clear_s: float = 1800.0
    heartbeat_s: float = 600.0
    pump_danger_from: int = 3           # FWI class 'high'
    flame_recheck_s: float = 30.0       # after a first flame read in Normal, wake again this soon (0 = off)


@dataclass
class Inputs:
    gas_smoke: bool = False
    gas_fault: bool = False
    flame: bool = False
    camera: tuple = None                # (label, confidence) when a capture finished
    fwi_mode: str = "eco"
    fwi_danger: int = 0
    battery_low: bool = False
    housing_hot: bool = False
    supply_fault: bool = False
    dt_s: float = 30.0


@dataclass
class Output:
    state: int
    interval_s: float
    camera_on: bool
    gps_on: bool
    actuator: bool
    reasons: int
    frames: list = field(default_factory=list)      # (kind, repeats)
    last_gasp: bool = False

    @property
    def state_name(self):
        return STATE_NAMES[self.state]


class StateMachine:
    def __init__(self, cfg=None):
        self.cfg = cfg or Config()
        self.state = NORMAL
        self.flame_reads = 0
        self.clear_count = 0
        self.fire_clear_s = 0.0
        self.since_frame_s = 0.0
        self.since_camera_s = self.cfg.camera_min_period_s
        self.last_gasp_sent = False
        self.reasons = 0
        self.survival = False

    def reset(self):
        """Operator or gateway acknowledgement: leave Fire."""
        self.state, self.clear_count, self.fire_clear_s, self.reasons = NORMAL, 0, 0.0, 0

    # ---- helpers -----------------------------------------------------------------------------------
    def _trigger_reasons(self, x):
        r = 0
        if x.gas_smoke:
            r |= R_GAS
        if self.flame_reads >= self.cfg.flame_reads_to_trigger:
            r |= R_FLAME
        return r

    def _camera_confirms(self, x):
        if x.camera is None:
            return False
        label, conf = x.camera
        return label in ("fire", "smoke") and conf >= self.cfg.camera_confidence

    def _normal_interval(self, x):
        if x.battery_low:
            return self.cfg.survival_interval_s
        return self.cfg.alert_interval_s if x.fwi_mode == "alert" else self.cfg.eco_interval_s

    # ---- one wake-up -------------------------------------------------------------------------------
    def step(self, x):
        c = self.cfg
        self.survival = x.battery_low
        self.flame_reads = self.flame_reads + 1 if x.flame else 0
        self.since_frame_s += x.dt_s
        self.since_camera_s += x.dt_s
        frames, previous = [], self.state
        trig = self._trigger_reasons(x)
        confirm = self._camera_confirms(x)
        if confirm:
            trig |= R_CAMERA
        # Survival: gas scans are suspended, only the flame sensor (hardware wake) can start a suspicion
        if x.battery_low:
            trig &= R_FLAME | R_CAMERA

        if self.state == NORMAL:
            if trig & (R_GAS | R_FLAME):
                self.state, self.clear_count = SUSPICION, 0
        elif self.state == SUSPICION:
            if confirm or (trig & R_GAS and trig & R_FLAME):
                self.state = FIRE
                frames.append(("alert", c.alert_repeats))
            elif trig & (R_GAS | R_FLAME):
                self.clear_count = 0
            else:
                self.clear_count += 1
                if self.clear_count >= c.clear_scans:
                    self.state = NORMAL
        elif self.state == FIRE:
            if trig:
                self.fire_clear_s = 0.0
            else:
                self.fire_clear_s += x.dt_s
                if self.fire_clear_s >= c.fire_hold_clear_s:
                    self.state, self.fire_clear_s = NORMAL, 0.0

        if self.state != previous and self.state != FIRE:
            frames.append(("state_change", 1))
        if self.state == FIRE and previous == FIRE and confirm:
            frames.append(("alert", 1))           # a new camera confirmation inside Fire is worth one more frame
        if not frames and self.since_frame_s >= c.heartbeat_s:
            frames.append(("heartbeat", 1))
        if frames:
            self.since_frame_s = 0.0

        self.reasons = trig if self.state != NORMAL else 0
        if self.state != NORMAL and x.fwi_danger >= c.pump_danger_from:
            self.reasons |= R_FWI

        last_gasp = False
        if (x.housing_hot or x.supply_fault) and not self.last_gasp_sent:
            last_gasp, self.last_gasp_sent = True, True
            frames.append(("last_gasp", c.alert_repeats))

        awake = self.state != NORMAL
        camera_on = awake and not x.battery_low and self.since_camera_s >= c.camera_min_period_s
        if camera_on:
            self.since_camera_s = 0.0
        interval = c.suspicion_interval_s if awake else self._normal_interval(x)
        if not awake and c.flame_recheck_s > 0 and 0 < self.flame_reads < c.flame_reads_to_trigger:
            interval = min(interval, c.flame_recheck_s)       # a first flame read is confirmed (or not) quickly
        pump = (self.state == FIRE) or (self.state == SUSPICION and x.fwi_danger >= c.pump_danger_from)
        return Output(self.state, interval, camera_on, gps_on=awake, actuator=pump, reasons=self.reasons,
                      frames=frames, last_gasp=last_gasp)
