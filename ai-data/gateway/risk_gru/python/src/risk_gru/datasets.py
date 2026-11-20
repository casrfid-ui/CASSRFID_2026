"""Data sources: S (synthetic, known truth), A (Algerian Forest Fires data set), P (hotspots + weather tables built on a PC)."""
import csv
import pathlib

import numpy as np

from gw_common import weather
from .features import season_table, CODES

# ------------------------------------------------------------------------------------------------ S: synthetic hazard
def hazard_logit(season, tau=4.0, variant="additive"):
    """Latent fuel moisture (time constant `tau` days) + dry streak + 3-day maximum wind + heat wave. Returns logit(p) per day,
    where day u's hazard uses the weather up to day u-1 (so the next-day target is exactly computable from known history)."""
    n = len(season["temp"])
    m = np.zeros(n)
    m[0] = 14.0
    k = 1.0 - np.exp(-1.0 / tau)
    eq = np.clip(4.0 + 0.30 * season["rh"] - 0.10 * (season["temp"] - 20.0), 3.0, 30.0)
    for i in range(1, n):
        m[i] = min(m[i - 1] + (eq[i] - m[i - 1]) * k + 0.8 * season["rain"][i], 40.0)
    streak = np.zeros(n)
    for i in range(1, n):
        streak[i] = 0 if season["rain"][i] >= 1.0 else min(streak[i - 1] + 1, 20)
    wmax3 = np.array([season["wind"][max(0, i - 2):i + 1].max() for i in range(n)])
    hw = season["heatwave"].astype(float)
    z = -0.30 * (m - 12.0) + 0.05 * wmax3 + 0.06 * streak + 0.6 * hw
    if variant == "interaction":                        # S2: memory that is not additive: a long heat wave multiplies the wind effect
        run = np.zeros(n)
        for i in range(1, n):
            run[i] = min(run[i - 1] + 1, 10) if hw[i] > 0 else 0
        z = -0.30 * (m - 12.0) + 0.02 * wmax3 + 0.03 * streak + 0.35 * run * (wmax3 / 20.0) ** 2
    out = np.empty(n)
    out[0] = z[0]
    out[1:] = z[:-1]                                    # hazard of day u from the state of day u-1
    return out


def _intercept(zs, target):
    """b0 such that the mean daily fire probability (days 30 on) equals `target`: bisection on the generator, not a fitted model."""
    z = np.concatenate([x[30:] for x in zs])
    lo, hi = -30.0, 30.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if (1.0 / (1.0 + np.exp(-(z + mid)))).mean() > target:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)


def synthetic(n_years=40, seed=0, prevalence=0.06, variant="additive", **kw):
    """List of season tables with Bernoulli fires drawn from the hazard, plus the true probability `p_true` (the oracle)."""
    rng = np.random.default_rng(seed)
    tables = []
    seasons = weather.simulate_years(n_years, seed=seed)
    zs = [hazard_logit(s, variant=variant, **kw) for s in seasons]
    b0 = _intercept(zs, prevalence)
    for s, z in zip(seasons, zs):
        p = 1.0 / (1.0 + np.exp(-(z + b0)))
        fire = (rng.random(len(p)) < p).astype(float)
        t = season_table(s["doy"], s["temp"], s["rh"], s["wind"], s["rain"], fire, group=f"Y{s['year']:02d}")
        t["p_true"] = p
        tables.append(t)
    return tables


# ------------------------------------------------------------------------------------------------ A: Algerian data set
def algerian(path):
    """Two season tables (Bejaia, Sidi Bel-abbes), noon values of June to September 2012, with the published FWI codes.
    The file has two blocks, one per region, each with its own header line."""
    rows, site = [], None
    for line in open(path, encoding="utf-8", errors="replace"):
        line = line.strip()
        if not line:
            continue
        if "Region" in line and "day" not in line:
            site = "Bejaia" if "Bejaia" in line else "SidiBelAbbes"
            continue
        if line.startswith("day,"):
            continue
        p = [x.strip() for x in line.split(",")]
        if len(p) < 14 or not p[0].isdigit():
            continue
        rows.append((site, p))
    tables = []
    for s in ("Bejaia", "SidiBelAbbes"):
        r = [p for st, p in rows if st == s]
        doy = [int((np.datetime64(f"{int(p[2]):04d}-{int(p[1]):02d}-{int(p[0]):02d}") - np.datetime64("2012-01-01")).astype(int)) + 1 for p in r]
        f = lambda j: [float(p[j]) for p in r]
        fire = [1.0 if p[13].lower().startswith("fire") else 0.0 if p[13].lower().startswith("not") else float("nan") for p in r]   # one row has no label: NaN, windows touching it are dropped
        cg = dict(ffmc=f(7), dmc=f(8), dc=f(9), isi=f(10), bui=f(11), fwi=f(12))
        tables.append(season_table(doy, f(3), f(4), f(5), f(6), fire, group=s, codes_given=cg))
    return tables


# ------------------------------------------------------------------------------------------------ P: PC-built tables
def from_weather_and_hotspots(weather_csv, hotspot_csv, site_lat, site_lon, radius_km=10.0, min_conf=("n", "h", "nominal", "high")):
    """Level P adapter. weather_csv columns: date (YYYY-MM-DD), temp, rh, wind, rain (noon values, rain = 24 h total ending at noon).
    hotspot_csv: NASA FIRMS archive download (columns latitude, longitude, acq_date, confidence, ...). A day is a fire day when a
    hotspot with accepted confidence lies within `radius_km` of the site. Returns one season table per calendar year (April to October)."""
    w = list(csv.DictReader(open(weather_csv)))
    hs = list(csv.DictReader(open(hotspot_csv)))
    fire_days = set()
    for h in hs:
        if str(h.get("confidence", "")).strip().lower() not in min_conf:
            continue
        lat, lon = float(h["latitude"]), float(h["longitude"])
        dy = (lat - site_lat) * 111.0
        dx = (lon - site_lon) * 111.0 * np.cos(np.radians(site_lat))
        if dx * dx + dy * dy <= radius_km ** 2:
            fire_days.add(h["acq_date"])
    by_year = {}
    for r in w:
        d = np.datetime64(r["date"])
        y = int(str(d)[:4])
        doy = int((d - np.datetime64(f"{y}-01-01")).astype(int)) + 1
        if 91 <= doy <= 304:
            by_year.setdefault(y, []).append((doy, float(r["temp"]), float(r["rh"]), float(r["wind"]), float(r["rain"]), 1.0 if r["date"] in fire_days else 0.0))
    out = []
    for y, rr in sorted(by_year.items()):
        rr.sort()
        a = np.array(rr)
        out.append(season_table(a[:, 0], a[:, 1], a[:, 2], a[:, 3], a[:, 4], a[:, 5], group=f"{site_lat:.2f}_{site_lon:.2f}_{y}"))
    return out
