"""Fire-front arrival times on a grid.

Physics used (all constants are PLACEHOLDERS to be replaced by a fuel calibration; none was fitted to a Mediterranean fire):
  head rate        R = a (1 - exp(-b ISI))^c * fuel         [m/min]
  length/breadth   LB = 1 + 8.729 (1 - exp(-0.030 W))^2.155   (W = wind speed km/h; Canadian FBP form for open fuels - to verify against the primary reference)
  slope factor     exp(+/- 3.533 |s|^1.2) per edge, s = rise/run along that edge, + uphill, - downhill, clipped to [0.2, 5] (FBP upslope form, symmetric extension is OUR assumption)
Ellipse with the ignition at a focus. With e = sqrt(1 - 1/LB^2) and phi the angle between the ray and the head direction (downwind),
the front moves along a ray at   r(phi) = R (1 - e) / (1 - e cos phi)   (head: R, back: R (1-e)/(1+e), flank: R (1-e); derivation in the notebook).
Arrival time: Dijkstra over 16 neighbours; an edge costs length / r(phi_edge) / slope / fuel."""
import heapq
import math

import numpy as np

# 16-neighbour offsets (dx, dy): the 8 king moves + 8 knight moves
OFFSETS = [(1, 0), (2, 1), (1, 1), (1, 2), (0, 1), (-1, 2), (-1, 1), (-2, 1), (-1, 0), (-2, -1), (-1, -1), (-1, -2), (0, -1), (1, -2), (1, -1), (2, -1)]

A_HEAD, B_HEAD, C_HEAD = 45.0, 0.05, 1.2          # placeholder fuel parameters (m/min)


def head_rate(isi, a=A_HEAD, b=B_HEAD, c=C_HEAD):
    return a * (1.0 - math.exp(-b * max(isi, 0.0))) ** c


def length_to_breadth(wind_kmh):
    return 1.0 + 8.729 * (1.0 - math.exp(-0.030 * max(wind_kmh, 0.0))) ** 2.155


def slope_factor(s):
    f = math.exp(math.copysign(3.533 * abs(s) ** 1.2, s))
    return min(max(f, 0.2), 5.0)


class FireSpread:
    """`elevation`: (ny, nx) metres or None. `fuel`: (ny, nx) multiplier (0 = unburnable) or None. `cell`: metres."""

    def __init__(self, ny, nx, cell=20.0, elevation=None, fuel=None):
        self.ny, self.nx, self.cell = ny, nx, float(cell)
        self.z = np.zeros((ny, nx)) if elevation is None else np.asarray(elevation, float)
        self.fuel = np.ones((ny, nx)) if fuel is None else np.asarray(fuel, float)

    def edge_times(self, isi, wind_kmh, wind_to_deg, rate_scale=1.0):
        """Per-offset arrays (ny, nx) of the time in minutes to go from each cell to its neighbour. `wind_to_deg`: direction the wind blows TOWARDS, degrees clockwise from north.
        The grid has x to the east and y to the north."""
        R = head_rate(isi) * rate_scale
        LB = length_to_breadth(wind_kmh)
        e = math.sqrt(max(1.0 - 1.0 / LB ** 2, 0.0))
        head = math.radians(90.0 - wind_to_deg)               # math angle of the head direction (counter-clockwise from east)
        out = []
        for dx, dy in OFFSETS:
            dist = self.cell * math.hypot(dx, dy)
            phi = math.atan2(dy, dx) - head
            r = R * (1.0 - e) / (1.0 - e * math.cos(phi))
            t = np.full((self.ny, self.nx), np.inf)
            ys, xs = slice(max(0, -dy), self.ny - max(0, dy)), slice(max(0, -dx), self.nx - max(0, dx))
            yt, xt = slice(max(0, dy), self.ny + min(0, dy)), slice(max(0, dx), self.nx + min(0, dx))
            s = (self.z[yt, xt] - self.z[ys, xs]) / dist
            sf = np.clip(np.exp(np.sign(s) * 3.533 * np.abs(s) ** 1.2), 0.2, 5.0)
            fu = np.minimum(self.fuel[ys, xs], self.fuel[yt, xt])
            with np.errstate(divide="ignore"):
                t[ys, xs] = np.where(fu > 0, dist / (r * sf * fu), np.inf)
            out.append(t)
        return out

    def arrival(self, ignition, isi, wind_kmh, wind_to_deg, rate_scale=1.0):
        """Arrival time (min) at every cell. `ignition`: (ix, iy). Dijkstra, 16 neighbours."""
        ny, nx = self.ny, self.nx
        et = [t.ravel().tolist() for t in self.edge_times(isi, wind_kmh, wind_to_deg, rate_scale)]
        dist = [math.inf] * (ny * nx)
        src = ignition[1] * nx + ignition[0]
        dist[src] = 0.0
        heap = [(0.0, src)]
        offs = [dy * nx + dx for dx, dy in OFFSETS]
        pop, push = heapq.heappop, heapq.heappush
        while heap:
            d, u = pop(heap)
            if d > dist[u]:
                continue
            ux, uy = u % nx, u // nx
            for k, (dx, dy) in enumerate(OFFSETS):
                vx, vy = ux + dx, uy + dy
                if 0 <= vx < nx and 0 <= vy < ny:
                    w = et[k][u]
                    if w != math.inf:
                        nd = d + w
                        v = u + offs[k]
                        if nd < dist[v]:
                            dist[v] = nd
                            push(heap, (nd, v))
        return np.array(dist).reshape(ny, nx)

    @staticmethod
    def isochrones(arrival, minutes=(15, 30, 60)):
        return {m: arrival <= m for m in minutes}
