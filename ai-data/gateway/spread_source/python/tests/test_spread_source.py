import math
import time
import numpy as np
import pytest

from spread_source import FireSpread, SourceLocator, head_rate, length_to_breadth, concentration, receptor_unit_response


def extents(arr, cell, T, ix, iy):
    m = arr <= T
    xs = np.where(m.any(0))[0]; ys = np.where(m.any(1))[0]
    return (xs.max() - ix) * cell, (ix - xs.min()) * cell, (ys.max() - ys.min()) * cell, (xs.max() - xs.min()) * cell


def test_circle_no_wind_flat():
    fs = FireSpread(121, 121, cell=10.0)
    arr = fs.arrival((60, 60), isi=15, wind_kmh=0.0, wind_to_deg=0.0)
    R = head_rate(15)
    yy, xx = np.mgrid[0:121, 0:121]
    d = np.hypot(xx - 60, yy - 60) * 10.0
    m = d > 50
    err = np.abs(arr[m] - d[m] / R) / (d[m] / R)
    assert err.mean() <= 0.04, err.mean()


@pytest.mark.parametrize("wind", [8.0, 15.0])
def test_ellipse_extents(wind):
    cell, n = 5.0, 360
    fs = FireSpread(301, n, cell=cell)
    ix, iy, T = 60, 150, 60.0
    arr = fs.arrival((ix, iy), isi=15, wind_kmh=wind, wind_to_deg=90.0)       # blows towards east
    R, LB = head_rate(15), length_to_breadth(wind)
    e = math.sqrt(1 - 1 / LB ** 2)
    head, back, width, length = extents(arr, cell, T, ix, iy)
    assert abs(head - R * T) / (R * T) <= 0.05
    assert abs(back - R * T * (1 - e) / (1 + e)) / (R * T * (1 - e) / (1 + e)) <= 0.05
    assert abs(length / width - LB) / LB <= 0.08


def test_monotone_physics():
    assert head_rate(5) < head_rate(10) < head_rate(25)
    z = np.tile(np.arange(61) * 5.0, (61, 1))                     # rises towards east (slope 0.5/ cell width 10 m -> s = 0.5)
    fs = FireSpread(61, 61, cell=10.0, elevation=z * 0.4)
    arr = fs.arrival((30, 30), isi=10, wind_kmh=0.0, wind_to_deg=0.0)
    assert arr[30, 40] < arr[30, 20]                              # uphill (east) reached before downhill (west)
    iso = fs.isochrones(arr)
    assert (iso[15] <= iso[30]).all() and (iso[30] <= iso[60]).all()


def test_runtime_100x100():
    fs = FireSpread(100, 100, cell=20.0)
    t0 = time.perf_counter(); fs.arrival((50, 50), isi=12, wind_kmh=15, wind_to_deg=45); dt = time.perf_counter() - t0
    assert dt < 1.0, dt


@pytest.mark.parametrize("x", [1000.0, 2000.0, 4000.0])
def test_plume_mass_conservation(x):
    u = 4.0
    ys = np.linspace(-1500, 1500, 3001); zs = np.linspace(0, 1500, 3001)
    Y, Z = np.meshgrid(ys, zs)
    flux = np.trapezoid(np.trapezoid(concentration(x, Y, Z, u) * u, ys, axis=1), zs)
    assert abs(flux - 1.0) <= 0.02, flux


def test_source_found_with_four_boxes_and_two_boxes_ambiguous():
    rng = np.random.default_rng(0)
    loc = SourceLocator((-2000, 2000, -2000, 2000), cell=50.0)
    src = (200.0, -100.0); wd, u = 60.0, 5.0
    th = math.radians(90 - wd)
    frame = lambda xd, yc: (src[0] + xd * math.cos(th) - yc * math.sin(th), src[1] + xd * math.sin(th) + yc * math.cos(th))
    boxes = [frame(800, 60), frame(1200, -80), frame(1600, 30), frame(1000, -150)]     # downwind frame (along, across) in metres
    depth = [receptor_unit_response(src, b, wd, u) * 1e4 * math.exp(rng.normal(0, 0.3)) for b in boxes]
    post = loc.posterior(boxes, depth, wd, u)
    s = loc.summarize(post, boxes)
    assert math.hypot(s["map_xy"][0] - src[0], s["map_xy"][1] - src[1]) <= 500
    s2 = loc.summarize(loc.posterior(boxes[:2], depth[:2], wd, u), boxes[:2])
    assert s2["area90_m2"] > s["area90_m2"]
