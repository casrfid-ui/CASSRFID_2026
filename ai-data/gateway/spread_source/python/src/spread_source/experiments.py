"""Source-localisation trials (synthetic truth)."""
import math

import numpy as np

from .plume import receptor_unit_response
from .source import SourceLocator

Q0 = 1e4          # emission strength in the unit of the readings (readings are unit-free in the simulation)


def one_trial(rng, n_boxes, loc, sigma=0.3, domain=4000.0, core=1500.0, d0=1e-3, mode="random"):
    half = domain / 2
    src = (rng.uniform(-core / 2, core / 2), rng.uniform(-core / 2, core / 2))
    wd, u = rng.uniform(0, 360), rng.uniform(3, 8)
    if mode == "random":              # boxes anywhere in the domain, wind in any direction: the plume often misses them all
        boxes = [(rng.uniform(-half, half), rng.uniform(-half, half)) for _ in range(n_boxes)]
    else:                            # "in_plume": favourable geometry, boxes 500-3000 m downwind, crosswind offset ~ N(0, 0.7 sigma_y) (best case, NOT typical)
        from .plume import sigma_yz
        th = math.radians(90.0 - wd)
        boxes = []
        for _ in range(n_boxes):
            xd = rng.uniform(500, 3000); yc = rng.normal(0, 0.7 * float(sigma_yz(xd)[0]))
            boxes.append((src[0] + xd * math.cos(th) - yc * math.sin(th), src[1] + xd * math.sin(th) + yc * math.cos(th)))
    clean = np.array([receptor_unit_response(src, b, wd, u) * Q0 for b in boxes])
    depth = clean * np.exp(rng.normal(0, sigma, n_boxes))
    depth = np.where(clean > 0, depth, 0.0)
    ndet = int((depth >= d0).sum())
    out = dict(ndet=ndet, src=src)
    if ndet >= 1:
        post = loc.posterior(boxes, depth, wd, u)
        s = loc.summarize(post, boxes)
        out.update(err=math.hypot(s["map_xy"][0] - src[0], s["map_xy"][1] - src[1]), area90=s["area90_m2"])
    return out


def run(n_boxes, n_trials=200, seed=0, sigma=0.3, mode="random"):
    loc = SourceLocator((-4000, 4000, -4000, 4000), cell=50.0, sigma=sigma) if mode != "random" else SourceLocator((-2000, 2000, -2000, 2000), cell=50.0, sigma=sigma)
    rng = np.random.default_rng(seed)
    return [one_trial(rng, n_boxes, loc, sigma, mode=mode) for _ in range(n_trials)]


def summarize(trials, min_det=1, tol=500.0):
    t = [x for x in trials if x["ndet"] >= min_det]
    if not t:
        return dict(n=0)
    err = np.array([x["err"] for x in t]); ar = np.array([x["area90"] for x in t])
    return dict(n=len(t), frac_alarm=len(t) / len(trials), success=float((err <= tol).mean()), median_err=float(np.median(err)), median_area90_km2=float(np.median(ar) / 1e6))
