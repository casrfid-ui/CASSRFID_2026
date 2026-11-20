"""A scripted fire story on a 7-box network, written as real 16-byte FFP frames so every byte goes through the gateway's
normal path: decode, registry, fusion, alert levels, dispatch, slow path, dashboard.

Site: forested hills of north-west Tunisia (illustrative positions, configurable). 7 boxes about 600 m apart on two rows,
gateway on the ridge to the north-east, drone base on the forest road, spare gateway to the south-west.
Wind (simulated) blows toward the north-east, so smoke from a fire near box 6 reaches boxes 7, 2 and 3.

Box ids 1..7 are the protocol's range for one gateway (ids 8..11 are gateways).

Story (scenario seconds, scaled by `speed`):
  0    all boxes report position, weather (wind and rain flagged simulated) and Normal heartbeats; danger class high.
       Boxes 1 and 5, far from the gateway, are heard through their neighbour (mesh relay flag).
  30   fire weather worsens: danger class very high -> L1, every box moves to Alert mode
  40   box 1 goes silent (no frame any more) -> L4 box lost after 2.5 heartbeats
  60   box 6 gas score starts to rise; 80 smoke -> Suspicion (L2)
  95   the plume reaches box 7 (Suspicion) and, weaker, box 2 (gas bands) and box 3 (score only)
  110  box 6 flame vote positive, camera says fire -> FIRE (L3): SMS, email, drone mission. Only 3 boxes are in the
       plume, below the 4 the source locator needs, so the drone targets box 6 and the spread map starts there
  150  box 4 battery low -> L5 maintenance
  ...  after the operator acknowledges on the dashboard, boxes 6 and 7 return to Normal 25 s later
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]          # repository root
for p in (ROOT / "project" / "gateway" / "src", ROOT / "project" / "protocol" / "python"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from ffn_gateway import uart_link as U     # noqa: E402
from ffp import frame as F                 # noqa: E402

SITES = {
    1: ("Box 1, west ridge", 36.79610, 8.64580),
    2: ("Box 2, cork oak slope", 36.79530, 8.65290),
    3: ("Box 3, firebreak", 36.79580, 8.65980),
    4: ("Box 4, stream crossing", 36.79120, 8.66590),
    5: ("Box 5, west valley", 36.79010, 8.64480),
    6: ("Box 6, south slope", 36.78930, 8.65170),
    7: ("Box 7, trail junction", 36.78990, 8.65890),
}
GATEWAY_POS = (36.80020, 8.67050)
DRONE_BASE = (36.80180, 8.67630)
SPARE_GATEWAY = (36.78620, 8.64120)
RELAYED = {1, 5}


def _km(a, b):
    kx = 111.32 * math.cos(math.radians(a[0]))
    return math.hypot((a[0] - b[0]) * 110.54, (a[1] - b[1]) * kx)


@dataclass
class BoxSim:
    id: int
    seq: int = 0
    gas: float = 0.06
    battery: int = 90
    state: int = F.STATE_NORMAL
    flame: int = 0
    cam: tuple = (0, 0, 0)            # label, valid, conf (0..255)
    gas_class: int = F.GAS_NORMAL
    flags: int = 0
    band: tuple = (0, 0, 0)
    last_status: float = -1e9
    silent: bool = False

    def next_seq(self):
        self.seq = (self.seq + 1) & 0xFF
        return self.seq

    @property
    def radio(self):
        """RSSI / SNR*4 seen by the gateway: a simple distance model (relayed boxes are heard through the neighbour)."""
        _, la, lo = SITES[self.id]
        d = _km((la, lo), GATEWAY_POS)
        rssi = int(-76 - 11 * d - (5 if self.id in RELAYED else 0))
        snr4 = int((9.5 - 4.2 * d) * 4)
        return rssi, snr4


@dataclass
class Scenario:
    speed: float = 1.0
    t0: float = 0.0
    boxes: dict = field(default_factory=lambda: {i: BoxSim(i, battery=b) for i, b in
                                                 zip(range(1, 8), (77, 91, 86, 31, 68, 94, 88))})
    danger: int = 3
    fwi: float = 27.5
    acked_at: float | None = None
    recovered: bool = False
    started: bool = False
    vision_sent: bool = False
    last_telem_s: float = 0.0
    frames_out: int = 0
    last_bridge: float = -1e9

    def st(self, now):                # scenario seconds
        return (now - self.t0) * self.speed

    # ---------------------------------------------------------------- frame builders
    def _flags(self, b: BoxSim, extra=0):
        return F.F_SIM_WX | (F.F_RELAYED if b.id in RELAYED else 0) | extra

    def _status_frame(self, b: BoxSim, type_):
        reasons = 0
        if b.gas_class == F.GAS_SMOKE: reasons |= F.R_GAS
        if b.flame: reasons |= F.R_FLAME
        if b.cam[0] in (F.CAM_FIRE, F.CAM_SMOKE) and b.cam[1]: reasons |= F.R_CAMERA
        if self.danger >= 4: reasons |= F.R_FWI
        mode = F.MODE_ALERT if (self.danger >= 4 or b.state) else F.MODE_ECO
        s = F.Status(state=b.state, mode=mode, reasons=reasons, gas_score=int(min(1, b.gas) * 255), gas_class=b.gas_class,
                     flame=b.flame, cam_label=b.cam[0], cam_valid=b.cam[1], cam_conf=b.cam[2], flags=b.flags,
                     fwi_x2=int(self.fwi * 2), danger=self.danger, fwi_updated=1, battery_pct=b.battery, band=b.band)
        return F.make(type_, b.id, 0, b.next_seq(), s, self._flags(b, F.F_ACK_REQ | F.F_PRIORITY if type_ == F.T_ALERT else 0))

    def _telem_frame(self, b: BoxSim):
        hot = 1 if self.danger >= 4 else 0
        _, la, _ = SITES[b.id]
        t = F.Telem(temp_c100=int((31.5 + 3 * hot + (36.80 - la) * 60) * 100), rh_x2=int((27 - 6 * hot) * 2), wind_kmh=22 + 6 * hot,
                    rain_x10=0, ffmc_x2_5=int((90.5 + 2 * hot) * 2.5), dmc=48 + 6 * hot, dc=430 + 10 * hot, isi_x5=int((11 + 7 * hot) * 5),
                    bui=74 + 6 * hot, history_hours=24)
        return F.make(F.T_TELEM, b.id, 0, b.next_seq(), t, self._flags(b))

    def _pos_frame(self, b: BoxSim):
        _, lat, lon = SITES[b.id]
        return F.make(F.T_POS, b.id, 0, b.next_seq(), F.Pos(int(lat * 1e7), int(lon * 1e7), 610 + 12 * b.id, 9, 1), self._flags(b) & ~F.F_SIM_WX)

    # ---------------------------------------------------------------- the story
    def step(self, now: float, gw) -> list:
        """Advance the story to `now` and return the messages (RxFrame, BridgeStatus) for the gateway."""
        out = []

        def rx(b: BoxSim, fr):
            if b.silent:
                return
            rssi, snr4 = b.radio
            self.frames_out += 1
            out.append(U.RxFrame(rssi, snr4, fr.encode()))

        if not self.started:
            self.started, self.t0 = True, now
            for b in self.boxes.values():
                rx(b, self._pos_frame(b))
                rx(b, self._telem_frame(b))
        s = self.st(now)
        bx = self.boxes
        changed = set()

        if s >= 30 and self.danger < 4:
            self.danger, self.fwi = 4, 41.0
            for b in bx.values():
                rx(b, self._telem_frame(b)); changed.add(b.id)
        if s >= 40 and not bx[1].silent:
            bx[1].silent = True                                   # box 1 stops transmitting (power or radio fault)
        if not self.recovered:
            b6 = bx[6]
            if 60 <= s < 110 and b6.state != F.STATE_FIRE:
                g = min(0.62, 0.06 + (s - 60) * 0.012)
                if abs(g - b6.gas) > 0.05:
                    b6.gas = g; b6.band = (int(10 + g * 40), int(4 + g * 30), int(2 + g * 12)); changed.add(6)
            if s >= 80 and b6.state == F.STATE_NORMAL:
                b6.gas_class, b6.state, b6.cam = F.GAS_SMOKE, F.STATE_SUSPICION, (F.CAM_BACKGROUND, 1, 40)
                changed.add(6)
            if s >= 95 and bx[7].state == F.STATE_NORMAL:
                b7 = bx[7]
                b7.gas, b7.gas_class, b7.state, b7.band, b7.cam = 0.41, F.GAS_SMOKE, F.STATE_SUSPICION, (22, 14, 6), (F.CAM_SMOKE, 1, 96)
                for i, (g, band) in ((2, (0.19, (9, 5, 2))), (3, (0.14, (0, 0, 0)))):
                    bx[i].gas, bx[i].band = g, band
                changed |= {2, 3, 7}
            if s >= 110 and b6.state == F.STATE_SUSPICION:
                b6.flame, b6.cam, b6.state, b6.gas, b6.band = 1, (F.CAM_FIRE, 1, 214), F.STATE_FIRE, 0.74, (48, 40, 22)
                rx(b6, self._status_frame(b6, F.T_ALERT))
                if not self.vision_sent and hasattr(gw, "on_camera_event"):
                    self.vision_sent = True
                    gw.on_camera_event(6, "fire", 0.88, 41.0, now)
        if s >= 150 and not bx[4].flags & F.SF_BATTERY_LOW:
            bx[4].battery, bx[4].flags = 13, bx[4].flags | F.SF_BATTERY_LOW
            changed.add(4)
        # recovery after the operator acknowledgement
        if bx[6].state == F.STATE_FIRE and gw.alerts.operator_ack and self.acked_at is None:
            self.acked_at = now
        if self.acked_at is not None and not self.recovered and (now - self.acked_at) * self.speed >= 25:
            self.recovered = True
            for i in (6, 7):
                b = bx[i]
                b.state, b.flame, b.cam, b.gas, b.gas_class, b.band = F.STATE_NORMAL, 0, (0, 1, 20), 0.1, F.GAS_NORMAL, (2, 1, 0)
            for i in (2, 3):
                bx[i].gas, bx[i].band = 0.07, (0, 0, 0)
            changed |= {2, 3, 6, 7}

        for b in bx.values():
            period = 6 if b.state == F.STATE_FIRE else 20
            if b.id in changed or (now - b.last_status) * self.speed >= period:
                b.last_status = now
                t = F.T_ALERT if b.state == F.STATE_FIRE else (F.T_STATE if b.id in changed else F.T_HEARTBEAT)
                rx(b, self._status_frame(b, t))
        if (now - self.last_bridge) * self.speed >= 10:
            # the ESP32 bridge reports its own status over the UART (simulated in this demo: no serial link)
            self.last_bridge = now
            out.append(U.BridgeStatus(int(s), True, True, bx[6].state == F.STATE_FIRE, True, 0, 18, self.frames_out, self.frames_out, 0))
        if s - self.last_telem_s >= 120:
            self.last_telem_s = s
            for b in bx.values():
                rx(b, self._telem_frame(b))
        return out


def demo_gateway_config(dashboard_url: str, api_port: int, missions_dir: str, push_s: float = 0.0,
                        api_token: str = "demo-gateway", ingest_token: str = "demo-ingest") -> dict:
    return {
        "db_path": ":memory:", "serial_port": "", "gateway_id": 8,
        "boxes": [{"id": i, "name": n, "lat": la, "lon": lo} for i, (n, la, lo) in SITES.items()],
        "phone_numbers": ["+000000000001", "+000000000002"], "emails": ["operator@example.org"],
        "dashboard_url": dashboard_url, "dashboard_token": ingest_token, "dashboard_push_s": push_s,
        "api_host": "127.0.0.1", "api_port": api_port, "api_token": api_token,
        "heartbeat_s": 40.0, "slow_path_period_s": 30.0,
        "drone": {"enabled": True, "base_lat": DRONE_BASE[0], "base_lon": DRONE_BASE[1], "missions_dir": missions_dir},
        "sim_wind_to_deg": 60.0,
    }
