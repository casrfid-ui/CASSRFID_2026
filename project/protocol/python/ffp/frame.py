from __future__ import annotations

import struct
from dataclasses import dataclass, field, fields

FRAME_LEN = 16
PAYLOAD_LEN = 12

T_ALERT, T_STATE, T_HEARTBEAT, T_LAST_GASP, T_TELEM, T_POS, T_ACK, T_CMD, T_TIME = 1, 2, 3, 4, 5, 6, 8, 9, 10
BOX_TYPES = (T_ALERT, T_STATE, T_HEARTBEAT, T_LAST_GASP, T_TELEM, T_POS)
DOWN_TYPES = (T_ACK, T_CMD, T_TIME)
TYPE_NAMES = {1: "alert", 2: "state", 3: "heartbeat", 4: "last_gasp", 5: "telem", 6: "pos", 8: "ack", 9: "cmd", 10: "time"}

F_SIM_WX, F_RELAYED, F_ACK_REQ, F_PRIORITY = 1, 2, 4, 8
ID_ANY_GW, ID_BROADCAST = 0, 15
BOX_IDS = range(1, 8)
GW_IDS = range(8, 12)

# status flags
SF_BATTERY_LOW, SF_HOUSING_HOT, SF_SUPPLY_FAULT, SF_CLOCK_UNSYNCED, SF_STORAGE_ERROR, SF_GPS_ON, SF_PUMP, SF_CAMERA_ON = 1, 2, 4, 8, 16, 32, 64, 128
MODE_ECO, MODE_ALERT, MODE_SURVIVAL = 0, 1, 2
STATE_NORMAL, STATE_SUSPICION, STATE_FIRE = 0, 1, 2
R_GAS, R_FLAME, R_CAMERA, R_FWI = 1, 2, 4, 8
GAS_NORMAL, GAS_SMOKE, GAS_DECOY, GAS_FAULT = 0, 1, 2, 3
CAM_BACKGROUND, CAM_FIRE, CAM_SMOKE = 0, 1, 2

# commands
C_SET_THRESH, C_RISK_PRIOR, C_FORCE_MODE, C_RESET_FIRE, C_SIM_WX, C_SET_SF, C_PING = 1, 2, 3, 4, 5, 6, 7
AF_OPERATOR, AF_SBC_UP, AF_FROM_BRIDGE = 1, 2, 4


class FrameError(ValueError):
    """Raised by decode with .code equal to the C return value (-1 length, -2 crc, -3 type, -4 ids)."""

    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code


def crc8(data: bytes) -> int:
    c = 0
    for b in data:
        c ^= b
        for _ in range(8):
            c = ((c << 1) ^ 0x07) & 0xFF if c & 0x80 else (c << 1) & 0xFF
    return c


def q8(x: float, scale: float) -> int:
    if x != x:
        return 0
    v = int(__import__("math").floor(x * scale + 0.5))
    return max(0, min(255, v))


@dataclass
class Frame:
    type: int
    origin: int
    dest: int = ID_ANY_GW
    seq: int = 0
    flags: int = 0
    payload: bytes = bytes(PAYLOAD_LEN)

    @property
    def simulated_wx(self):
        return bool(self.flags & F_SIM_WX)

    @property
    def relayed(self):
        return bool(self.flags & F_RELAYED)

    def key(self):
        """Identity used for de-duplication: the same frame heard directly, repeated, or relayed."""
        return (self.origin, self.seq, self.type)

    def encode(self) -> bytes:
        if self.type not in BOX_TYPES + DOWN_TYPES or not (0 <= self.origin <= 15 and 0 <= self.dest <= 15 and 0 <= self.flags <= 15):
            raise FrameError(-1, "cannot encode")
        if len(self.payload) != PAYLOAD_LEN:
            raise FrameError(-1, "payload must be 12 bytes")
        b = bytes([(self.type << 4) | self.flags, (self.origin << 4) | self.dest, self.seq & 0xFF]) + bytes(self.payload)
        return b + bytes([crc8(b)])


def decode(data: bytes) -> Frame:
    if len(data) != FRAME_LEN:
        raise FrameError(-1, "length")
    if crc8(data[:15]) != data[15]:
        raise FrameError(-2, "crc")
    t = data[0] >> 4
    if t not in BOX_TYPES + DOWN_TYPES:
        raise FrameError(-3, "type")
    origin, dest = data[1] >> 4, data[1] & 15
    if (t in BOX_TYPES and origin not in BOX_IDS) or (t in DOWN_TYPES and origin not in GW_IDS):
        raise FrameError(-4, "ids")
    return Frame(t, origin, dest, data[2], data[0] & 15, bytes(data[3:15]))


@dataclass
class Status:
    state: int = 0
    mode: int = 0
    reasons: int = 0
    gas_score: int = 0
    gas_class: int = 0
    gas_faults: int = 0
    warmup: int = 0
    flame: int = 0
    scan_bad: int = 0
    cam_label: int = 0
    cam_valid: int = 0
    cam_status: int = 0
    cam_conf: int = 0
    flags: int = 0
    fwi_x2: int = 0
    danger: int = 0
    fwi_updated: int = 0
    provisional: int = 0
    repeat: int = 0
    battery_pct: int = 0
    band: tuple = (0, 0, 0)

    score = property(lambda s: s.gas_score / 255.0)
    cam_confidence = property(lambda s: s.cam_conf / 255.0)
    fwi = property(lambda s: s.fwi_x2 / 2.0)
    bands = property(lambda s: tuple(b / 64.0 for b in s.band))
    depth = property(lambda s: max(s.band) / 64.0)

    def pack(self) -> bytes:
        p = bytearray(PAYLOAD_LEN)
        p[0] = (self.state & 3) | ((self.mode & 3) << 2) | ((self.reasons & 15) << 4)
        p[1] = self.gas_score
        p[2] = (self.gas_class & 3) | ((self.gas_faults & 7) << 2) | ((self.warmup & 1) << 5) | ((self.flame & 1) << 6) | ((self.scan_bad & 1) << 7)
        p[3] = (self.cam_label & 3) | ((self.cam_valid & 1) << 2) | ((self.cam_status & 15) << 3)
        p[4], p[5], p[6] = self.cam_conf, self.flags, self.fwi_x2
        p[7] = (self.danger & 7) | ((self.fwi_updated & 1) << 3) | ((self.provisional & 1) << 4) | ((self.repeat & 3) << 5)
        p[8] = self.battery_pct
        p[9], p[10], p[11] = self.band
        return bytes(p)

    @classmethod
    def unpack(cls, p: bytes) -> "Status":
        return cls(state=p[0] & 3, mode=(p[0] >> 2) & 3, reasons=(p[0] >> 4) & 15, gas_score=p[1],
                   gas_class=p[2] & 3, gas_faults=(p[2] >> 2) & 7, warmup=(p[2] >> 5) & 1, flame=(p[2] >> 6) & 1, scan_bad=(p[2] >> 7) & 1,
                   cam_label=p[3] & 3, cam_valid=(p[3] >> 2) & 1, cam_status=(p[3] >> 3) & 15, cam_conf=p[4], flags=p[5], fwi_x2=p[6],
                   danger=p[7] & 7, fwi_updated=(p[7] >> 3) & 1, provisional=(p[7] >> 4) & 1, repeat=(p[7] >> 5) & 3,
                   battery_pct=p[8], band=(p[9], p[10], p[11]))


@dataclass
class Telem:
    temp_c100: int = 0
    rh_x2: int = 0
    wind_kmh: int = 0
    rain_x10: int = 0
    ffmc_x2_5: int = 0
    dmc: int = 0
    dc: int = 0
    isi_x5: int = 0
    bui: int = 0
    history_hours: int = 0
    provisional: int = 0

    temp = property(lambda s: s.temp_c100 / 100.0)
    rh = property(lambda s: s.rh_x2 / 2.0)
    rain_mm = property(lambda s: s.rain_x10 / 10.0)
    ffmc = property(lambda s: s.ffmc_x2_5 / 2.5)
    isi = property(lambda s: s.isi_x5 / 5.0)

    def pack(self) -> bytes:
        return struct.pack(">hBBBBBHBBB", self.temp_c100, self.rh_x2, self.wind_kmh, self.rain_x10, self.ffmc_x2_5, self.dmc, self.dc,
                           self.isi_x5, self.bui, (self.history_hours & 31) | ((self.provisional & 1) << 5))

    @classmethod
    def unpack(cls, p: bytes) -> "Telem":
        t, rh, w, r, f, d, dc, i, b, h = struct.unpack(">hBBBBBHBBB", bytes(p))
        return cls(t, rh, w, r, f, d, dc, i, b, h & 31, (h >> 5) & 1)


@dataclass
class Pos:
    lat_e7: int = 0
    lon_e7: int = 0
    alt_m: int = 0
    sats: int = 0
    fix: int = 0

    lat = property(lambda s: s.lat_e7 / 1e7)
    lon = property(lambda s: s.lon_e7 / 1e7)

    def pack(self) -> bytes:
        return struct.pack(">iihBB", self.lat_e7, self.lon_e7, self.alt_m, self.sats, self.fix)

    @classmethod
    def unpack(cls, p: bytes) -> "Pos":
        return cls(*struct.unpack(">iihBB", bytes(p)))


@dataclass
class Ack:
    acked_seq: int = 0
    acked_type: int = 0
    flags: int = 0
    rssi_dbm: int = 0
    snr_x4: int = 0
    gw_id: int = 8
    alert_level: int = 0

    def pack(self) -> bytes:
        return struct.pack(">BBBbbBB", self.acked_seq, self.acked_type, self.flags, max(-128, min(127, self.rssi_dbm)),
                           max(-128, min(127, self.snr_x4)), self.gw_id, self.alert_level) + bytes(5)

    @classmethod
    def unpack(cls, p: bytes) -> "Ack":
        return cls(*struct.unpack(">BBBbbBB", bytes(p[:7])))


@dataclass
class Cmd:
    id: int = 0
    arg: tuple = (0, 0, 0, 0, 0, 0)

    def pack(self) -> bytes:
        a = tuple(self.arg) + (0,) * (6 - len(self.arg))
        return bytes([self.id]) + bytes(a[:6]) + bytes(5)

    @classmethod
    def unpack(cls, p: bytes) -> "Cmd":
        return cls(p[0], tuple(p[1:7]))


@dataclass
class TimeSync:
    unix_s: int = 0
    utc_offset_q: int = 0

    def pack(self) -> bytes:
        return struct.pack(">Ib", self.unix_s, self.utc_offset_q) + bytes(7)

    @classmethod
    def unpack(cls, p: bytes) -> "TimeSync":
        return cls(*struct.unpack(">Ib", bytes(p[:5])))


_BODY = {T_ALERT: Status, T_STATE: Status, T_HEARTBEAT: Status, T_LAST_GASP: Status, T_TELEM: Telem, T_POS: Pos, T_ACK: Ack, T_CMD: Cmd, T_TIME: TimeSync}


def body_of(frame: Frame):
    """The typed payload of a decoded frame."""
    return _BODY[frame.type].unpack(frame.payload)


def make(type_: int, origin: int, dest: int, seq: int, body, flags: int = 0) -> Frame:
    return Frame(type_, origin, dest, seq, flags, body.pack())
