"""The six components of the Canadian FWI system as pure functions (Van Wagner 1987; hourly FFMC Van Wagner 1977).

Units: temperature degC, relative humidity %, wind km/h, rain mm. Daily functions take the noon observation and 24 h rain."""
import math

# Day-length adjustment, 12 months (Van Wagner 1987, 46 N). Replaced per latitude by `day_length_tables`.
LE_46N = (6.5, 7.5, 9.0, 12.8, 13.9, 13.9, 12.4, 10.9, 9.4, 8.0, 7.0, 6.0)
LF_46N = (-1.6, -1.6, -1.6, 0.9, 3.8, 5.8, 6.4, 5.0, 2.4, 0.4, -1.6, -1.6)


def _moisture_from_ffmc(f, c=147.2):
    """Fine fuel moisture content (%) from the FFMC."""
    return c * (101.0 - f) / (59.5 + f)


def _ffmc_from_moisture(m, c=147.2):
    return min(max(59.5 * (250.0 - m) / (c + m), 0.0), 101.0)


def _rain_adjusted(mo, rf):
    """Moisture after rain `rf` (mm effective). Same equation for daily and hourly."""
    mr = mo + 42.5 * rf * math.exp(-100.0 / (251.0 - mo)) * (1.0 - math.exp(-6.93 / rf))
    if mo > 150.0:
        mr += 0.0015 * (mo - 150.0) ** 2 * math.sqrt(rf)
    return min(mr, 250.0)


def _equilibria(rh, temp):
    """Drying and wetting equilibrium moisture contents."""
    common = 0.18 * (21.1 - temp) * (1.0 - math.exp(-0.115 * rh))
    ed = 0.942 * rh ** 0.679 + 11.0 * math.exp((rh - 100.0) / 10.0) + common
    ew = 0.618 * rh ** 0.753 + 10.0 * math.exp((rh - 100.0) / 10.0) + common
    return ed, ew


def _relax(mo, rh, temp, wind, ed, ew, rate_factor, steps):
    """Move the moisture toward the equilibrium (drying if above Ed, wetting if below Ew), `steps` periods long."""
    if mo > ed:
        ko = 0.424 * (1.0 - (rh / 100.0) ** 1.7) + 0.0694 * math.sqrt(wind) * (1.0 - (rh / 100.0) ** 8)
        kd = ko * rate_factor * math.exp(0.0365 * temp)
        return ed + (mo - ed) * 10.0 ** (-kd * steps)
    if mo < ew:
        k1 = 0.424 * (1.0 - ((100.0 - rh) / 100.0) ** 1.7) + 0.0694 * math.sqrt(wind) * (1.0 - ((100.0 - rh) / 100.0) ** 8)
        kw = k1 * rate_factor * math.exp(0.0365 * temp)
        return ew - (ew - mo) * 10.0 ** (-kw * steps)
    return mo


def ffmc_daily(f0, temp, rh, wind, rain):
    """Daily Fine Fuel Moisture Code. 0.5 mm of rain is intercepted by the canopy."""
    rh = min(rh, 100.0)
    mo = _moisture_from_ffmc(f0)
    if rain > 0.5:
        mo = _rain_adjusted(mo, rain - 0.5)
    ed, ew = _equilibria(rh, temp)
    return _ffmc_from_moisture(_relax(mo, rh, temp, wind, ed, ew, 0.581, 1))


def ffmc_hourly(f0, temp, rh, wind, rain, hours=1.0):
    """Hourly FFMC (Van Wagner 1977 as in the cffdrs package): any rain counts, the rate factor is 0.0579 per hour."""
    rh = min(rh, 100.0)
    mo = _moisture_from_ffmc(f0, 147.27723)
    if rain > 0.0:
        mo = _rain_adjusted(mo, rain)
    ed, ew = _equilibria(rh, temp)
    return _ffmc_from_moisture(_relax(mo, rh, temp, wind, ed, ew, 0.0579, hours), 147.27723)


def dmc(p0, temp, rh, rain, month, le=LE_46N):
    """Daily Duff Moisture Code. `le` is the 12-value day-length factor table."""
    t = max(temp, -1.1)
    if rain > 1.5:
        re = 0.92 * rain - 1.27
        mo = 20.0 + 280.0 / math.exp(0.023 * p0)          # CFS (cffdrs) form; the 1987 paper writes exp(5.6348 - p0/43.43)
        if p0 <= 33.0:
            b = 100.0 / (0.5 + 0.3 * p0)
        elif p0 <= 65.0:
            b = 14.0 - 1.3 * math.log(p0)
        else:
            b = 6.2 * math.log(p0) - 17.2
        mr = mo + 1000.0 * re / (48.77 + b * re)
        p0 = max(43.43 * (5.6348 - math.log(mr - 20.0)), 0.0)
    k = 1.894 * (t + 1.1) * (100.0 - rh) * le[month - 1] * 1e-6
    return p0 + 100.0 * k


def dc(d0, temp, rain, month, lf=LF_46N):
    """Daily Drought Code. `lf` is the 12-value day-length adjustment table."""
    t = max(temp, -2.8)
    if rain > 2.8:
        rd = 0.83 * rain - 1.27
        qo = 800.0 * math.exp(-d0 / 400.0)
        qr = qo + 3.937 * rd
        d0 = max(400.0 * math.log(800.0 / qr), 0.0)
    v = max(0.36 * (t + 2.8) + lf[month - 1], 0.0)
    return d0 + 0.5 * v


def isi(f, wind):
    """Initial Spread Index from the FFMC and the wind."""
    m = _moisture_from_ffmc(f)
    f_w = math.exp(0.05039 * wind)
    f_f = 91.9 * math.exp(-0.1386 * m) * (1.0 + m ** 5.31 / 4.93e7)
    return 0.208 * f_w * f_f


def bui(p, d):
    """Build-up Index from the DMC and the DC."""
    if p <= 0.4 * d:
        u = 0.8 * p * d / (p + 0.4 * d) if (p + 0.4 * d) > 0 else 0.0
    else:
        u = p - (1.0 - 0.8 * d / (p + 0.4 * d)) * (0.92 + (0.0114 * p) ** 1.7)
    return max(u, 0.0)


def fwi(isi_value, bui_value):
    """Fire Weather Index."""
    if bui_value <= 80.0:
        f_d = 0.626 * bui_value ** 0.809 + 2.0
    else:
        f_d = 1000.0 / (25.0 + 108.64 * math.exp(-0.023 * bui_value))
    b = 0.1 * isi_value * f_d
    return b if b <= 1.0 else math.exp(2.72 * (0.434 * math.log(b)) ** 0.647)
