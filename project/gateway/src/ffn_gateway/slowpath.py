"""Slow path: runs every few minutes in a background thread (or once, on demand). Produces the predictions shown on the
dashboard. Never blocks, and never decides an alert: the fast path (fusion + alerts) does not wait for it."""
from __future__ import annotations

import datetime as dt
import math
import time

import numpy as np

from .ffp import frame as F


MIN_BOXES_FOR_SOURCE = 4      # below this the localisation is not reliable (71 % within 500 m only with 4 boxes in the plume)


class LocalFrame:
    def __init__(self, lat0, lon0):
        self.lat0, self.lon0 = lat0, lon0
        self.kx = 111320.0 * math.cos(math.radians(lat0))
        self.ky = 110540.0

    def xy(self, lat, lon):
        return (lon - self.lon0) * self.kx, (lat - self.lat0) * self.ky

    def ll(self, x, y):
        return self.lat0 + y / self.ky, self.lon0 + x / self.kx


class SlowPath:
    def __init__(self, cfg, registry, models, store, assess_fn=None):
        self.cfg, self.reg, self.m, self.store = cfg, registry, models, store
        self.risk: dict[int, object] = {}
        self.trend: dict[int, object] = {}
        self.last_day: dict[int, str] = {}
        self.last_scan_t: dict[int, float] = {}
        self.results: dict = {}
        self.updated = 0.0
        self.assess_fn = assess_fn      # callable returning the current Assessment (to know about a fire)

    # ---- helpers
    def _frame(self):
        boxes = [b for b in self.reg.boxes.values() if b.lat or b.lon]
        lat0 = self.cfg.origin_lat or (boxes[0].lat if boxes else 0.0)
        lon0 = self.cfg.origin_lon or (boxes[0].lon if boxes else 0.0)
        return LocalFrame(lat0, lon0)

    @staticmethod
    def _day_row(b, now):
        t, s = b.last_telem, b.last_status
        if not t or not s:
            return None
        month = dt.datetime.fromtimestamp(now, dt.timezone.utc).month
        return dict(temp=t.temp, rh=t.rh, wind=float(t.wind_kmh), rain=t.rain_mm, ffmc=t.ffmc, dmc=float(t.dmc), dc=float(t.dc),
                    isi=t.isi, bui=float(t.bui), fwi=s.fwi, month=month)

    # ---- per-model steps (each isolated: one failure never stops the others)
    def _risk(self, now):
        out = {}
        if not self.m.risk_cls:
            return out
        today = dt.datetime.fromtimestamp(now, dt.timezone.utc).strftime("%Y-%m-%d")
        for b in self.reg.boxes.values():
            row = self._day_row(b, now)
            if row is None or b.last_telem is None or b.last_telem.provisional:
                continue
            p = self.risk.get(b.id) or self.risk.setdefault(b.id, self.m.risk_cls(self.m.risk_path))
            if self.last_day.get(b.id) != today:
                self.last_day[b.id] = today
                out[b.id] = p.update(row)
            elif b.id in self.results.get("risk", {}):
                out[b.id] = self.results["risk"][b.id]
        return out

    def _forecast(self, now):
        out = {}
        if not self.m.forecaster:
            return out
        doy = dt.datetime.fromtimestamp(now, dt.timezone.utc).timetuple().tm_yday
        for b in self.reg.boxes.values():
            t = b.last_telem
            if not t or t.provisional:
                continue
            out[b.id] = self.m.forecaster.forecast((t.ffmc, float(t.dmc), float(t.dc)),
                                                   dict(temp=t.temp, rh=t.rh, wind=float(t.wind_kmh), rain=t.rain_mm), doy)
        return out

    def _trend(self, now):
        out = {}
        if not self.m.trend_cls:
            return out
        for b in self.reg.boxes.values():
            s, t = b.last_status, b.last_telem
            if not s or s.warmup or b.last_status_t <= self.last_scan_t.get(b.id, 0):
                continue
            self.last_scan_t[b.id] = b.last_status_t
            p = self.trend.get(b.id) or self.trend.setdefault(b.id, self.m.trend_cls(self.m.trend_path))
            out[b.id] = p.update(s.score, s.depth, list(s.bands), t.temp if t else 20.0, t.rh if t else 50.0)
        return out or self.results.get("trend", {})

    def _wind(self):
        """Wind speed is a measured value only when no box flags simulated weather; direction is never measured (simulated)."""
        ws = [b.last_telem.wind_kmh for b in self.reg.boxes.values() if b.last_telem]
        kmh = float(np.mean(ws)) if ws else 5.0
        return kmh, self.cfg.sim_wind_to_deg, True

    def _fire_geometry(self, now):
        a = self.assess_fn() if self.assess_fn else None
        if not (a and a.fire_boxes) or not self.m.spread_mod:
            return {}
        fr = self._frame()
        bx = [self.reg.get(i) for i in a.fire_boxes]
        isi = max((b.last_telem.isi for b in bx if b.last_telem), default=8.0)
        kmh, to_deg, simulated = self._wind()
        cell, n = 50.0, 80                       # 4 km square, 50 m cells
        x0, y0 = fr.xy(bx[0].lat, bx[0].lon)
        ext = (x0 - n * cell / 2, x0 + n * cell / 2, y0 - n * cell / 2, y0 + n * cell / 2)
        res = {"wind_kmh": kmh, "wind_to_deg": to_deg, "wind_direction_simulated": simulated, "fuel": "placeholder constants"}
        # source: use box depths
        boxes = [self.reg.get(i) for i in self.reg.boxes]
        det = [(b, b.last_status.depth) for b in boxes if b.last_status and b.lat]
        ix, iy = n // 2, n // 2
        if det and any(d >= 1e-3 for _, d in det):
            loc = self.m.source_mod.SourceLocator(ext, cell)
            xy = [fr.xy(b.lat, b.lon) for b, _ in det]
            post = loc.posterior(xy, [max(d, 1e-6) for _, d in det], to_deg, max(kmh / 3.6, 0.5))
            sm = loc.summarize(post, xy)
            sx, sy = sm["map_xy"]
            lat, lon = fr.ll(sx, sy)
            res["source"] = {"lat": lat, "lon": lon, "area50_m2": sm["area50_m2"], "area90_m2": sm["area90_m2"],
                             "n_boxes_detecting": int(sum(d >= 1e-3 for _, d in det)),
                             "note": "reliable only with >= 4 boxes in the plume"}
            res["source"]["used_as_ignition"] = res["source"]["n_boxes_detecting"] >= MIN_BOXES_FOR_SOURCE
            if res["source"]["used_as_ignition"]:
                ix = int(np.clip((sx - ext[0]) / cell, 0, n - 1)); iy = int(np.clip((sy - ext[2]) / cell, 0, n - 1))
        fs = self.m.spread_mod.FireSpread(n, n, cell)
        arr = fs.arrival((ix, iy), isi, kmh, to_deg)
        iso = {}
        for mins, mask in fs.isochrones(arr, (15, 30, 60)).items():
            ys, xs = np.nonzero(mask)
            if len(xs) == 0:
                continue
            x_lo, x_hi = ext[0] + xs.min() * cell, ext[0] + (xs.max() + 1) * cell
            y_lo, y_hi = ext[2] + ys.min() * cell, ext[2] + (ys.max() + 1) * cell
            (la0, lo0), (la1, lo1) = fr.ll(x_lo, y_lo), fr.ll(x_hi, y_hi)
            iso[str(mins)] = {"area_m2": float(mask.sum() * cell * cell), "bbox": [la0, lo0, la1, lo1]}
        res["isochrones"] = iso
        res["ignition"] = dict(zip(("lat", "lon"), fr.ll(ext[0] + (ix + .5) * cell, ext[2] + (iy + .5) * cell)))
        return res

    # ---- run
    def run_once(self, now=None):
        now = time.time() if now is None else now
        res = {}
        for name, fn in (("risk", lambda: self._risk(now)), ("fwi_forecast", lambda: self._forecast(now)),
                         ("trend", lambda: self._trend(now)), ("fire", lambda: self._fire_geometry(now))):
            try:
                res[name] = fn()
            except Exception as e:
                res[name] = {}
                res.setdefault("errors", {})[name] = repr(e)
        self.results, self.updated = res, now
        return res
