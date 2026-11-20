"""Bayesian grid inversion of the smoke source.

Model: depth_i = Q * c_i(s) * lognormal(0, sigma) for a box that detects; a box that reads below `detect_limit` is censored
(evidence that it is NOT in the plume). Q (emission strength, unit-free) is profiled out on the detecting boxes.
Prior: uniform on the grid. Output: posterior over the grid, MAP, credible areas, bearing from each box to the MAP."""
import math

import numpy as np

from .plume import receptor_unit_response

try:
    from math import erf
except ImportError:      # pragma: no cover
    erf = None


def _phi(z):
    return 0.5 * (1.0 + np.vectorize(math.erf)(np.asarray(z, float) / math.sqrt(2.0)))


class SourceLocator:
    def __init__(self, extent, cell=50.0, sigma=0.3, detect_limit=1e-3, z=2.0):
        """`extent`: (xmin, xmax, ymin, ymax) metres in the gateway's local frame."""
        self.cell, self.sigma, self.d0, self.z = cell, sigma, detect_limit, z
        xs = np.arange(extent[0] + cell / 2, extent[1], cell)
        ys = np.arange(extent[2] + cell / 2, extent[3], cell)
        self.gx, self.gy = np.meshgrid(xs, ys)

    def posterior(self, boxes, depths, wind_to_deg, wind_speed_ms):
        """`boxes`: list of (x, y); `depths`: reading of each box (same unit as detect_limit). Returns (ny, nx) posterior (sums to 1)."""
        depths = np.asarray(depths, float)
        det = depths >= self.d0
        ll = np.zeros(self.gx.shape)
        C = np.stack([receptor_unit_response((self.gx, self.gy), b, wind_to_deg, wind_speed_ms, self.z) for b in boxes])   # (n_box, ny, nx)
        floor = 1e-12
        if det.any():
            lc = np.log(np.maximum(C[det], floor))
            r = np.log(depths[det])[:, None, None] - lc
            logq = r.mean(0)                                                    # profile Q
            ll += -((r - logq) ** 2).sum(0) / (2 * self.sigma ** 2)
            qhat = np.exp(logq)
        else:
            qhat = np.full(self.gx.shape, self.d0 / floor)
        for k in np.where(~det)[0]:                                              # clean boxes: P(reading < limit)
            mu = np.log(np.maximum(qhat * C[k], floor))
            p = _phi((np.log(self.d0) - mu) / self.sigma)
            ll += np.log(np.maximum(p, 1e-300))
        ll -= ll.max()
        post = np.exp(ll)
        return post / post.sum()

    def summarize(self, post, boxes):
        i = np.unravel_index(np.argmax(post), post.shape)
        mx, my = float(self.gx[i]), float(self.gy[i])
        order = np.argsort(post.ravel())[::-1]
        cum = np.cumsum(post.ravel()[order])
        area = lambda lvl: float((np.searchsorted(cum, lvl) + 1) * self.cell ** 2)
        bearings = [float((math.degrees(math.atan2(mx - bx, my - by))) % 360.0) for bx, by in boxes]
        return dict(map_xy=(mx, my), area50_m2=area(0.5), area90_m2=area(0.9), bearings_deg=bearings)
