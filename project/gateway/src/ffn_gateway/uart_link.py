"""Link between the SBC and the gateway bridge (ESP32): HDLC-like framing, message codecs and a transport.

Mirror of firmware/gateway_bridge/core/src/hdlc.c: 0x7E | type | payload | crc16 | 0x7E, 0x7D escaping,
CRC-16/CCITT-FALSE over type + payload. The transport is pluggable: a real serial port, or an in-memory pair for tests.
"""
from __future__ import annotations

import queue
import struct
import threading
from dataclasses import dataclass

FLAG, ESC, XOR = 0x7E, 0x7D, 0x20
MAX_PAYLOAD = 120

# bridge -> SBC
BR_RX_FRAME, BR_STATUS, BR_SMS_RESULT, BR_EMERGENCY = 0x01, 0x02, 0x03, 0x04
# SBC -> bridge
SB_HELLO, SB_TX_FRAME, SB_SEND_SMS, SB_DISPATCHED, SB_BYE, SB_SET_NUMBERS, SB_SET_LEVEL, SB_SET_TIME, SB_PING = (
    0x80, 0x81, 0x82, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88)


def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def encode(type_: int, payload: bytes = b"") -> bytes:
    if len(payload) > MAX_PAYLOAD:
        raise ValueError("payload too large")
    body = bytes([type_]) + bytes(payload)
    body += struct.pack(">H", crc16(body))
    out = bytearray([FLAG])
    for b in body:
        if b in (FLAG, ESC):
            out += bytes([ESC, b ^ XOR])
        else:
            out.append(b)
    out.append(FLAG)
    return bytes(out)


@dataclass
class Msg:
    type: int
    data: bytes


class Decoder:
    def __init__(self):
        self.buf = bytearray()
        self.in_frame = False
        self.escape = False
        self.bad_crc = 0
        self.overflow = 0

    def feed(self, chunk: bytes) -> list[Msg]:
        out = []
        for b in chunk:
            if b == FLAG:
                if self.in_frame and len(self.buf) >= 3:
                    body = bytes(self.buf[:-2])
                    if crc16(body) == struct.unpack(">H", bytes(self.buf[-2:]))[0]:
                        out.append(Msg(body[0], body[1:]))
                    else:
                        self.bad_crc += 1
                self.buf.clear()
                self.in_frame, self.escape = True, False
            elif not self.in_frame:
                continue
            elif b == ESC:
                self.escape = True
            else:
                if self.escape:
                    b ^= XOR
                    self.escape = False
                if len(self.buf) > MAX_PAYLOAD + 3:
                    self.overflow += 1
                    self.buf.clear()
                    self.in_frame = False
                else:
                    self.buf.append(b)
        return out


# ------------------------------------------------------------------ typed messages
@dataclass
class RxFrame:
    rssi: int
    snr: int
    wire: bytes


@dataclass
class BridgeStatus:
    uptime_s: int
    sbc_up: bool
    modem_ready: bool
    alert_armed: bool
    have_time: bool
    pending: int
    csq: int
    frames_rx: int
    acks_tx: int
    crc_errors: int


@dataclass
class SmsResult:
    id: int
    status: int            # 0 = sent


@dataclass
class Emergency:
    box: int
    frame_type: int
    n_numbers: int         # the bridge already sent this many SMS


def parse(m: Msg):
    d = m.data
    if m.type == BR_RX_FRAME and len(d) == 18:
        return RxFrame(struct.unpack("b", d[0:1])[0], struct.unpack("b", d[1:2])[0], bytes(d[2:]))
    if m.type == BR_STATUS and len(d) == 13:
        up = struct.unpack(">I", d[:4])[0]
        fl = d[4]
        fr, ak, ce = struct.unpack(">HHH", d[7:13])
        return BridgeStatus(up, bool(fl & 1), bool(fl & 2), bool(fl & 4), bool(fl & 8), d[5], d[6], fr, ak, ce)
    if m.type == BR_SMS_RESULT and len(d) == 3:
        return SmsResult(d[0] | (d[1] << 8), d[2])
    if m.type == BR_EMERGENCY and len(d) == 3:
        return Emergency(d[0], d[1], d[2])
    return None


def hello() -> bytes: return encode(SB_HELLO)
def bye() -> bytes: return encode(SB_BYE)
def ping() -> bytes: return encode(SB_PING)
def dispatched(box: int) -> bytes: return encode(SB_DISPATCHED, bytes([box]))
def set_level(level: int) -> bytes: return encode(SB_SET_LEVEL, bytes([level]))
def set_numbers(numbers: list[str]) -> bytes: return encode(SB_SET_NUMBERS, ";".join(numbers).encode())


def set_time(unix_s: int, offset_q: int) -> bytes:
    return encode(SB_SET_TIME, struct.pack(">Ib", unix_s, offset_q))


def tx_frame(wire: bytes, immediate: bool = False) -> bytes:
    return encode(SB_TX_FRAME, bytes([1 if immediate else 0]) + wire)


def send_sms(sms_id: int, number: str, text: str) -> bytes:
    n = number.encode()
    t = text.encode("ascii", "replace")
    room = MAX_PAYLOAD - 3 - len(n)
    return encode(SB_SEND_SMS, struct.pack("<H", sms_id & 0x7FFF) + bytes([len(n)]) + n + t[:min(160, room)])


# ------------------------------------------------------------------ transports
class MemoryLink:
    """In-memory transport for tests and simulation. `inject()` plays the bridge; `sent` records what the SBC wrote."""

    def __init__(self):
        self._rx: "queue.Queue[bytes]" = queue.Queue()
        self.sent: list[Msg] = []
        self._dec = Decoder()
        self._lock = threading.Lock()

    def inject(self, type_: int, data: bytes = b""):
        self._rx.put(encode(type_, data))

    def inject_wire(self, wire: bytes, rssi: int = -90, snr: int = 20):
        self.inject(BR_RX_FRAME, struct.pack("bb", rssi, snr) + bytes(wire))

    def read(self, timeout: float = 0.0) -> bytes:
        try:
            return self._rx.get(timeout=timeout) if timeout else self._rx.get_nowait()
        except queue.Empty:
            return b""

    def write(self, data: bytes):
        with self._lock:
            self.sent.extend(self._dec.feed(data))

    def take_sent(self, type_: int | None = None) -> list[Msg]:
        with self._lock:
            out = [m for m in self.sent if type_ is None or m.type == type_]
            self.sent = [m for m in self.sent if not (type_ is None or m.type == type_)]
            return out

    def close(self):
        pass


class SerialLink:
    """Real serial port (pyserial is imported lazily so the package works without it)."""

    def __init__(self, port: str, baud: int = 115200):
        import serial  # type: ignore
        self._s = serial.Serial(port, baud, timeout=0.2)

    def read(self, timeout: float = 0.2) -> bytes:
        n = self._s.in_waiting
        return self._s.read(n or 1)

    def write(self, data: bytes):
        self._s.write(data)
        self._s.flush()

    def close(self):
        self._s.close()


class Link:
    """Message-level view on a transport: a reader thread decodes and queues parsed messages, `send` writes."""

    def __init__(self, transport):
        self.t = transport
        self.dec = Decoder()
        self.inbox: "queue.Queue" = queue.Queue()
        self._stop = threading.Event()
        self._th: threading.Thread | None = None

    def start(self):
        self._th = threading.Thread(target=self._run, name="uart-rx", daemon=True)
        self._th.start()
        self.send(hello())

    def _run(self):
        while not self._stop.is_set():
            chunk = self.t.read(0.05)
            if chunk:
                self.pump(chunk)

    def pump(self, chunk: bytes):
        for m in self.dec.feed(chunk):
            p = parse(m)
            if p is not None:
                self.inbox.put(p)

    def send(self, data: bytes):
        self.t.write(data)

    def stop(self):
        self._stop.set()
        try:
            self.send(bye())
        except Exception:
            pass
        if self._th:
            self._th.join(1.0)
        self.t.close()
