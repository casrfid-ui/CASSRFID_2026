"""Python reference of `runtime/c/src/box_runtime.c` (no flash, no reboot): same order, same time rules.

One call per wake-up: FWI once per local hour with the rain gathered since the previous one, gas chain on every
scan (ignored in Survival), state machine with the time since the previous wake-up."""
import calendar
import time
from dataclasses import dataclass, field

from flame import process as flame_process
from fwi import FwiEngine
from gas_chain import FAULT, SMOKE, GasChain
from state_machine import Inputs, StateMachine


@dataclass
class Tick:
    unix_s: int
    weather: tuple = None               # (temp_c, rh_pct, wind_kmh) or None when not read
    rain_mm: float = 0.0
    gas: tuple = None                   # (gas_ohm[10], temp_c[10], rh_pct[10]) or None when no scan
    flame: bool = False
    flame_raw: tuple = None             # burst of digital reads; when present it replaces `flame`
    camera: tuple = None                # (label, confidence) or None
    battery_low: bool = False
    housing_hot: bool = False
    supply_fault: bool = False


@dataclass
class TickOutput:
    sm: object
    fwi_updated: bool
    fwi: dict
    gas_scanned: bool
    gas_cls: int
    gas_score: float
    gas_warmup: bool


class BoxRuntime:
    def __init__(self, utc_offset_s=0):
        self.utc_offset_s = utc_offset_s
        self.fwi, self.gas, self.sm = FwiEngine(), GasChain(), StateMachine()
        self.fwi_last = dict(danger=0, mode="eco", fwi=0.0, ffmc=0.0, dmc=0.0, dc=0.0)
        self.gas_last = None
        self.last_unix = None
        self.last_gas_unix = None
        self.last_fwi_hour = None
        self.rain_acc = 0.0

    def step(self, t: Tick) -> TickOutput:
        dt = 0.0 if self.last_unix is None else float(max(0, t.unix_s - self.last_unix))
        self.last_unix = t.unix_s

        if t.rain_mm > 0:
            self.rain_acc += t.rain_mm
        local = t.unix_s + self.utc_offset_s
        hour_idx = local // 3600
        fwi_updated = False
        if t.weather is not None and (self.last_fwi_hour is None or hour_idx != self.last_fwi_hour):
            temp, rh, wind = t.weather
            month = time.gmtime(local).tm_mon
            o = self.fwi.update_hour(hour_idx % 24, month, temp, rh, wind, self.rain_acc)
            self.fwi_last = dict(danger=o.danger, mode=o.mode, fwi=o.fwi, ffmc=o.ffmc, dmc=o.dmc, dc=o.dc)
            self.rain_acc, self.last_fwi_hour, fwi_updated = 0.0, hour_idx, True

        scanned = False
        if t.gas is not None and not t.battery_low:
            dtg = 30.0 if self.last_gas_unix is None else float(t.unix_s - self.last_gas_unix)
            self.gas_last = self.gas.update(*t.gas, max(dtg, 1.0))
            self.last_gas_unix, scanned = t.unix_s, True
        g = self.gas_last
        cls = g.cls if g else 0
        flame = t.flame if t.flame_raw is None else flame_process(t.flame_raw).detected
        x = Inputs(gas_smoke=(not t.battery_low) and cls == SMOKE, gas_fault=cls == FAULT, flame=flame,
                   camera=t.camera, fwi_mode=self.fwi_last["mode"], fwi_danger=self.fwi_last["danger"],
                   battery_low=t.battery_low, housing_hot=t.housing_hot, supply_fault=t.supply_fault, dt_s=dt)
        out = self.sm.step(x)
        return TickOutput(out, fwi_updated, dict(self.fwi_last), scanned, cls, g.score if g else 0.0,
                          g.warmup if g else True)
