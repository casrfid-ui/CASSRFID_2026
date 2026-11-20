/* fwi.c - see fwi.h. Port of ai-data/box/fwi/python/src/fwi/{codes,engine,danger}.py */
#include "fwi.h"

#include <math.h>
#include <string.h>

const double fwi_le_46n[12] = {6.5, 7.5, 9.0, 12.8, 13.9, 13.9, 12.4, 10.9, 9.4, 8.0, 7.0, 6.0};
const double fwi_lf_46n[12] = {-1.6, -1.6, -1.6, 0.9, 3.8, 5.8, 6.4, 5.0, 2.4, 0.4, -1.6, -1.6};

static const double DANGER_THRESHOLDS[5] = {5.2, 11.2, 21.3, 38.0, 50.0};

/* ---- Components --------------------------------------------------------------------------- */
static double moisture_from_ffmc(double f, double c) { return c * (101.0 - f) / (59.5 + f); }

static double ffmc_from_moisture(double m, double c)
{
    double v = 59.5 * (250.0 - m) / (c + m);
    if (v < 0.0)   v = 0.0;
    if (v > 101.0) v = 101.0;
    return v;
}

static double rain_adjusted(double mo, double rf)
{
    double mr = mo + 42.5 * rf * exp(-100.0 / (251.0 - mo)) * (1.0 - exp(-6.93 / rf));
    if (mo > 150.0) mr += 0.0015 * (mo - 150.0) * (mo - 150.0) * sqrt(rf);
    return mr < 250.0 ? mr : 250.0;
}

static void equilibria(double rh, double temp, double *ed, double *ew)
{
    double common = 0.18 * (21.1 - temp) * (1.0 - exp(-0.115 * rh));
    *ed = 0.942 * pow(rh, 0.679) + 11.0 * exp((rh - 100.0) / 10.0) + common;
    *ew = 0.618 * pow(rh, 0.753) + 10.0 * exp((rh - 100.0) / 10.0) + common;
}

static double relax(double mo, double rh, double temp, double wind, double ed, double ew, double rate, double steps)
{
    if (mo > ed) {
        double ko = 0.424 * (1.0 - pow(rh / 100.0, 1.7)) + 0.0694 * sqrt(wind) * (1.0 - pow(rh / 100.0, 8.0));
        double kd = ko * rate * exp(0.0365 * temp);
        return ed + (mo - ed) * pow(10.0, -kd * steps);
    }
    if (mo < ew) {
        double q  = (100.0 - rh) / 100.0;
        double k1 = 0.424 * (1.0 - pow(q, 1.7)) + 0.0694 * sqrt(wind) * (1.0 - pow(q, 8.0));
        double kw = k1 * rate * exp(0.0365 * temp);
        return ew - (ew - mo) * pow(10.0, -kw * steps);
    }
    return mo;
}

double fwi_ffmc_daily(double f0, double temp, double rh, double wind, double rain)
{
    double ed, ew, mo;
    if (rh > 100.0) rh = 100.0;
    mo = moisture_from_ffmc(f0, 147.2);
    if (rain > 0.5) mo = rain_adjusted(mo, rain - 0.5);
    equilibria(rh, temp, &ed, &ew);
    return ffmc_from_moisture(relax(mo, rh, temp, wind, ed, ew, 0.581, 1.0), 147.2);
}

double fwi_ffmc_hourly(double f0, double temp, double rh, double wind, double rain, double hours)
{
    double ed, ew, mo;
    if (rh > 100.0) rh = 100.0;
    mo = moisture_from_ffmc(f0, 147.27723);
    if (rain > 0.0) mo = rain_adjusted(mo, rain);
    equilibria(rh, temp, &ed, &ew);
    return ffmc_from_moisture(relax(mo, rh, temp, wind, ed, ew, 0.0579, hours), 147.27723);
}

double fwi_dmc(double p0, double temp, double rh, double rain24, int month, const double *le)
{
    double t = temp > -1.1 ? temp : -1.1;
    double k;
    if (rain24 > 1.5) {
        double re = 0.92 * rain24 - 1.27;
        double mo = 20.0 + 280.0 / exp(0.023 * p0);
        double b, mr, v;
        if (p0 <= 33.0)      b = 100.0 / (0.5 + 0.3 * p0);
        else if (p0 <= 65.0) b = 14.0 - 1.3 * log(p0);
        else                 b = 6.2 * log(p0) - 17.2;
        mr = mo + 1000.0 * re / (48.77 + b * re);
        v  = 43.43 * (5.6348 - log(mr - 20.0));
        p0 = v > 0.0 ? v : 0.0;
    }
    k = 1.894 * (t + 1.1) * (100.0 - rh) * le[month - 1] * 1e-6;
    return p0 + 100.0 * k;
}

double fwi_dc(double d0, double temp, double rain24, int month, const double *lf)
{
    double t = temp > -2.8 ? temp : -2.8;
    double v;
    if (rain24 > 2.8) {
        double rd = 0.83 * rain24 - 1.27;
        double qo = 800.0 * exp(-d0 / 400.0);
        double qr = qo + 3.937 * rd;
        double x  = 400.0 * log(800.0 / qr);
        d0 = x > 0.0 ? x : 0.0;
    }
    v = 0.36 * (t + 2.8) + lf[month - 1];
    if (v < 0.0) v = 0.0;
    return d0 + 0.5 * v;
}

double fwi_isi(double ffmc, double wind)
{
    double m   = moisture_from_ffmc(ffmc, 147.2);
    double f_w = exp(0.05039 * wind);
    double f_f = 91.9 * exp(-0.1386 * m) * (1.0 + pow(m, 5.31) / 4.93e7);
    return 0.208 * f_w * f_f;
}

double fwi_bui(double p, double d)
{
    double u;
    if (p <= 0.4 * d) u = (p + 0.4 * d) > 0.0 ? 0.8 * p * d / (p + 0.4 * d) : 0.0;
    else              u = p - (1.0 - 0.8 * d / (p + 0.4 * d)) * (0.92 + pow(0.0114 * p, 1.7));
    return u > 0.0 ? u : 0.0;
}

double fwi_fwi(double isi, double bui)
{
    double f_d, b;
    if (bui <= 80.0) f_d = 0.626 * pow(bui, 0.809) + 2.0;
    else             f_d = 1000.0 / (25.0 + 108.64 * exp(-0.023 * bui));
    b = 0.1 * isi * f_d;
    return b <= 1.0 ? b : exp(2.72 * pow(0.434 * log(b), 0.647));
}

int fwi_danger_class(double fwi)
{
    int i, c = 0;
    for (i = 0; i < 5; i++) if (fwi >= DANGER_THRESHOLDS[i]) c++;
    return c;
}

fwi_mode_t fwi_mode_for_class(int danger)
{
    return danger >= FWI_ALERT_FROM_CLASS ? FWI_MODE_ALERT : FWI_MODE_ECO;
}

/* ---- State and persistence ---------------------------------------------------------------- */
void fwi_state_set_defaults(fwi_state_t *s)
{
    int i;
    s->ffmc = FWI_DEFAULT_FFMC;
    s->dmc  = FWI_DEFAULT_DMC;
    s->dc   = FWI_DEFAULT_DC;
    for (i = 0; i < FWI_RAIN_HOURS; i++) s->rain_mm[i] = FWI_DEFAULT_RAIN_MM;
    s->head = 0;
    s->real_hours = 0;
}

double fwi_rain_24h(const fwi_state_t *s)
{
    double sum = 0.0;
    int i;
    for (i = 0; i < FWI_RAIN_HOURS; i++) sum += s->rain_mm[(s->head + i) % FWI_RAIN_HOURS]; /* oldest first */
    return sum;
}

static uint32_t crc32(const uint8_t *p, size_t n)
{
    uint32_t c = 0xFFFFFFFFu;
    size_t i;
    int k;
    for (i = 0; i < n; i++) {
        c ^= p[i];
        for (k = 0; k < 8; k++) c = (c >> 1) ^ (0xEDB88320u & (0u - (c & 1u)));
    }
    return ~c;
}

#define BLOB_VERSION 1
#define BLOB_BODY    (FWI_BLOB_SIZE - 4)

fwi_status_t fwi_state_pack(const fwi_state_t *s, uint8_t buf[FWI_BLOB_SIZE])
{
    uint32_t crc;
    size_t o = 8;
    int i;
    if (!s || !buf) return FWI_ERR_ARG;
    memset(buf, 0, FWI_BLOB_SIZE);
    memcpy(buf, "FWIS", 4);
    buf[4] = BLOB_VERSION;
    buf[5] = s->head;
    buf[6] = s->real_hours;
    memcpy(buf + o, &s->ffmc, 8); o += 8;
    memcpy(buf + o, &s->dmc,  8); o += 8;
    memcpy(buf + o, &s->dc,   8); o += 8;
    for (i = 0; i < FWI_RAIN_HOURS; i++) { memcpy(buf + o, &s->rain_mm[i], 8); o += 8; }
    crc = crc32(buf, BLOB_BODY);
    buf[BLOB_BODY + 0] = (uint8_t)(crc);
    buf[BLOB_BODY + 1] = (uint8_t)(crc >> 8);
    buf[BLOB_BODY + 2] = (uint8_t)(crc >> 16);
    buf[BLOB_BODY + 3] = (uint8_t)(crc >> 24);
    return FWI_OK;
}

static int sane(double v, double lo, double hi) { return isfinite(v) && v >= lo && v <= hi; }

fwi_status_t fwi_state_unpack(fwi_state_t *s, const uint8_t *buf, size_t len)
{
    fwi_state_t t;
    uint32_t crc, want;
    size_t o = 8;
    int i;
    if (!s || !buf) return FWI_ERR_ARG;
    if (len != FWI_BLOB_SIZE || memcmp(buf, "FWIS", 4) != 0 || buf[4] != BLOB_VERSION) return FWI_ERR_BLOB;
    crc  = crc32(buf, BLOB_BODY);
    want = (uint32_t)buf[BLOB_BODY] | ((uint32_t)buf[BLOB_BODY + 1] << 8) |
           ((uint32_t)buf[BLOB_BODY + 2] << 16) | ((uint32_t)buf[BLOB_BODY + 3] << 24);
    if (crc != want) return FWI_ERR_BLOB;
    t.head = buf[5];
    t.real_hours = buf[6];
    memcpy(&t.ffmc, buf + o, 8); o += 8;
    memcpy(&t.dmc,  buf + o, 8); o += 8;
    memcpy(&t.dc,   buf + o, 8); o += 8;
    for (i = 0; i < FWI_RAIN_HOURS; i++) { memcpy(&t.rain_mm[i], buf + o, 8); o += 8; }
    if (t.head >= FWI_RAIN_HOURS || t.real_hours > FWI_RAIN_HOURS) return FWI_ERR_BLOB;
    if (!sane(t.ffmc, 0.0, 101.0) || !sane(t.dmc, 0.0, 1e4) || !sane(t.dc, 0.0, 1e4)) return FWI_ERR_BLOB;
    for (i = 0; i < FWI_RAIN_HOURS; i++) if (!sane(t.rain_mm[i], 0.0, 1e3)) return FWI_ERR_BLOB;
    *s = t;
    return FWI_OK;
}

/* ---- Engine ------------------------------------------------------------------------------- */
fwi_start_t fwi_engine_init(fwi_engine_t *e, const fwi_storage_t *storage, const double *le, const double *lf)
{
    uint8_t buf[FWI_BLOB_SIZE];
    e->le = le ? le : fwi_le_46n;
    e->lf = lf ? lf : fwi_lf_46n;
    e->storage = storage;
    fwi_state_set_defaults(&e->state);
    if (storage && storage->read) {
        int n = storage->read(storage->ctx, buf, sizeof buf);
        if (n == FWI_BLOB_SIZE && fwi_state_unpack(&e->state, buf, (size_t)n) == FWI_OK) return FWI_START_RESTORED;
        fwi_state_set_defaults(&e->state);   /* unpack leaves the state untouched on error, but be explicit */
    }
    return FWI_START_DEFAULTS;
}

static int input_ok(const fwi_input_t *in)
{
    return in->hour >= 0 && in->hour <= 23 && in->month >= 1 && in->month <= 12 &&
           sane(in->temp_c, -60.0, 70.0) && sane(in->rh_pct, 0.0, 105.0) &&
           sane(in->wind_kmh, 0.0, 300.0) && sane(in->rain_mm, 0.0, 500.0);
}

fwi_status_t fwi_engine_update_hour(fwi_engine_t *e, const fwi_input_t *in, fwi_output_t *out)
{
    fwi_state_t *s;
    double rh, isi, bui, f;
    if (!e || !in || !out) return FWI_ERR_ARG;
    if (!input_ok(in)) return FWI_ERR_INPUT;
    s  = &e->state;
    rh = in->rh_pct > 100.0 ? 100.0 : in->rh_pct;

    s->rain_mm[s->head] = in->rain_mm;                       /* overwrite the oldest hour */
    s->head = (uint8_t)((s->head + 1) % FWI_RAIN_HOURS);
    if (s->real_hours < FWI_RAIN_HOURS) s->real_hours++;

    s->ffmc = fwi_ffmc_hourly(s->ffmc, in->temp_c, rh, in->wind_kmh, in->rain_mm, 1.0);
    if (in->hour == FWI_NOON_HOUR) {
        double rain24 = fwi_rain_24h(s);
        s->dmc = fwi_dmc(s->dmc, in->temp_c, rh, rain24, in->month, e->le);
        s->dc  = fwi_dc(s->dc, in->temp_c, rain24, in->month, e->lf);
    }
    bui = fwi_bui(s->dmc, s->dc);
    isi = fwi_isi(s->ffmc, in->wind_kmh);
    f   = fwi_fwi(isi, bui);

    out->ffmc = s->ffmc; out->dmc = s->dmc; out->dc = s->dc;
    out->isi = isi; out->bui = bui; out->fwi = f;
    out->danger = (uint8_t)fwi_danger_class(f);
    out->mode = fwi_mode_for_class(out->danger);
    out->history_hours = s->real_hours;
    out->provisional = s->real_hours < FWI_RAIN_HOURS;
    out->saved = 0;
    if (e->storage && e->storage->write) {
        uint8_t buf[FWI_BLOB_SIZE];
        if (fwi_state_pack(s, buf) == FWI_OK && e->storage->write(e->storage->ctx, buf, sizeof buf) == 0) out->saved = 1;
    }
    return FWI_OK;
}
