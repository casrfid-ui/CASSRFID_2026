"""Synthetic Mediterranean fire-season weather (noon values), for method development when no multi-year record is available.

NOT a climate model of Tunisia. It reproduces the *kinds* of structure the models must cope with: a seasonal cycle, day-to-day
persistence, multi-day heat waves with dry air, wind events, and rain as a wet/dry Markov chain with a dry summer.
Every number below is an assumption chosen for plausibility (summer noon temperature 30 to 38 degC, RH 20 to 60 %), not fitted to data."""
import numpy as np

SEASON_START_DOY, SEASON_END_DOY = 91, 304          # 1 April .. 31 October
MONTH_STARTS = np.array([1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335])


def month_of(doy):
    return int(np.searchsorted(MONTH_STARTS, doy, side="right"))


def _season_curve(doy):
    """0 in winter, 1 at mid-summer (peak day 205)."""
    return 0.5 * (1 + np.cos(2 * np.pi * (doy - 205) / 365.0))


def simulate_year(rng, start=SEASON_START_DOY, end=SEASON_END_DOY, dryness=0.0):
    """One season. `dryness` in [-1, 1] shifts the whole year (drier > 0)."""
    doy = np.arange(start, end + 1)
    n = len(doy)
    s = _season_curve(doy)
    t_mean = 16.0 + 15.0 * s + 1.0 * dryness
    rh_mean = 82.0 - 24.0 * s - 5.0 * dryness
    # heat waves: 2-state chain, more frequent at high season
    hw = np.zeros(n, bool)
    for i in range(1, n):
        p_in = 0.015 + 0.035 * s[i]
        hw[i] = (rng.random() < p_in) if not hw[i - 1] else (rng.random() < 0.82)
    wind_ev = np.zeros(n, bool)                      # sirocco / strong wind events
    for i in range(1, n):
        wind_ev[i] = (rng.random() < 0.025) if not wind_ev[i - 1] else (rng.random() < 0.6)
    # AR(1) anomalies
    def ar1(phi, sigma):
        x = np.zeros(n)
        for i in range(1, n):
            x[i] = phi * x[i - 1] + rng.normal(0, sigma * np.sqrt(1 - phi ** 2))
        return x
    ta, ra, wa = ar1(0.75, 2.6), ar1(0.65, 7.0), ar1(0.5, 0.45)
    temp = t_mean + ta + 5.0 * hw + 2.0 * wind_ev
    rh = np.clip(rh_mean - 1.6 * ta + ra - 12.0 * hw - 10.0 * wind_ev, 6.0, 100.0)
    wind = np.exp(np.log(12.0) + wa + 0.5 * wind_ev) + 8.0 * wind_ev
    # rain: wet/dry chain, wet-day probability follows the season
    p_wd = np.clip(0.24 - 0.16 * s - 0.03 * dryness, 0.02, 0.4)
    wet = np.zeros(n, bool)
    for i in range(1, n):
        p = 0.45 if wet[i - 1] else p_wd[i]
        wet[i] = rng.random() < p
    amount = rng.gamma(0.6, 9.0, n)
    rain = np.where(wet, amount, 0.0)
    rh = np.where(wet, np.maximum(rh, 70.0 + 0 * rh), rh)
    temp = np.where(wet, temp - 3.0, temp)
    return dict(doy=doy, temp=temp, rh=rh, wind=np.clip(wind, 0.0, 50.0), rain=rain, heatwave=hw, wind_event=wind_ev)


def simulate_years(n_years, seed=0, **kw):
    """List of season dicts, each with its own dryness level drawn from N(0, 0.5)."""
    rng = np.random.default_rng(seed)
    out = []
    for y in range(n_years):
        d = float(np.clip(rng.normal(0, 0.5), -1, 1))
        season = simulate_year(rng, dryness=d, **kw)
        season["dryness"] = d
        season["year"] = y
        out.append(season)
    return out
