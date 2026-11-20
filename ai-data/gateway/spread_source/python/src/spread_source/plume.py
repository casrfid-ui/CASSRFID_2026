"""Steady Gaussian plume, ground-level point source, Briggs rural neutral (class D) dispersion.
Unit-free for the inversion: concentration per unit emission rate (s/m^3 when Q is in 1/s)."""
import numpy as np


def sigma_yz(x):
    x = np.maximum(np.asarray(x, float), 1.0)
    return 0.08 * x / np.sqrt(1.0 + 0.0001 * x), 0.06 * x / np.sqrt(1.0 + 0.0015 * x)


def concentration(x, y, z, u, Q=1.0, H=0.0):
    """x downwind, y crosswind, z height above ground (m). Ground reflection included. Zero for x <= 0."""
    x, y, z = np.broadcast_arrays(np.asarray(x, float), np.asarray(y, float), np.asarray(z, float))
    sy, sz = sigma_yz(x)
    c = (Q / (2 * np.pi * u * sy * sz)) * np.exp(-y ** 2 / (2 * sy ** 2)) * (np.exp(-(z - H) ** 2 / (2 * sz ** 2)) + np.exp(-(z + H) ** 2 / (2 * sz ** 2)))
    return np.where(x > 0, c, 0.0)


def receptor_unit_response(src_xy, rec_xy, wind_to_deg, u, z=2.0):
    """Concentration at receptors (per unit Q) for a source at src_xy; arrays broadcast. Coordinates in metres, x east, y north."""
    th = np.radians(90.0 - wind_to_deg)                         # math angle of the downwind direction
    dx, dy = np.asarray(rec_xy[0], float) - src_xy[0], np.asarray(rec_xy[1], float) - src_xy[1]
    xd = dx * np.cos(th) + dy * np.sin(th)
    yc = -dx * np.sin(th) + dy * np.cos(th)
    return concentration(xd, yc, z, u)
