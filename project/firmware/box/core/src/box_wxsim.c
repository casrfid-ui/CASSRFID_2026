#include "box_wxsim.h"

#include <math.h>

static double urand(box_wxsim_t *s)
{
    s->rng = s->rng * 1664525u + 1013904223u;
    return (double)(s->rng >> 8) / 16777216.0;
}

void box_wxsim_init(box_wxsim_t *s, uint32_t seed)
{
    s->rng = seed ? seed : 1u;
    s->wind_kmh = 10.0;
    s->rain_left_mm = 0.0;
    s->last_unix_s = 0;
    s->ovr = false; s->ovr_wind_kmh = 0; s->ovr_rain_x10 = 0; s->ovr_until_unix_s = 0;
}

void box_wxsim_override(box_wxsim_t *s, uint8_t wind_kmh, uint8_t rain_x10, int64_t until_unix_s)
{
    s->ovr = until_unix_s > 0;
    s->ovr_wind_kmh = wind_kmh; s->ovr_rain_x10 = rain_x10; s->ovr_until_unix_s = until_unix_s;
}

void box_wxsim_step(box_wxsim_t *s, int64_t unix_s, double *wind_kmh, double *rain_mm)
{
    double dt_h = 0.0, base, hour;
    if (s->last_unix_s > 0 && unix_s > s->last_unix_s) dt_h = (double)(unix_s - s->last_unix_s) / 3600.0;
    if (dt_h > 6.0) dt_h = 6.0;                      /* a long gap or a clock jump does not produce a storm */
    s->last_unix_s = unix_s;

    if (s->ovr && unix_s >= s->ovr_until_unix_s) s->ovr = false;
    if (s->ovr) {
        s->wind_kmh = s->ovr_wind_kmh;
        *wind_kmh = s->wind_kmh;
        *rain_mm = (double)s->ovr_rain_x10 / 10.0 * dt_h;
        return;
    }

    hour = fmod((double)unix_s / 3600.0, 24.0);
    base = 10.0 + 6.0 * sin(2.0 * 3.14159265358979323846 * (hour - 9.0) / 24.0);          /* windier in the afternoon */
    s->wind_kmh += (base - s->wind_kmh) * (dt_h > 1.0 ? 1.0 : dt_h) + (urand(s) - 0.5) * 6.0 * sqrt(dt_h > 0.0 ? dt_h : 0.0);
    if (s->wind_kmh < 0.0) s->wind_kmh = 0.0;
    if (s->wind_kmh > 60.0) s->wind_kmh = 60.0;
    *wind_kmh = s->wind_kmh;

    *rain_mm = 0.0;
    if (s->rain_left_mm <= 0.0 && urand(s) < 0.02 * dt_h) s->rain_left_mm = 0.5 + 4.5 * urand(s);   /* about one event per 2 days */
    if (s->rain_left_mm > 0.0) {
        double fall = 2.0 * dt_h;                                         /* 2 mm/h while it rains */
        if (fall > s->rain_left_mm) fall = s->rain_left_mm;
        s->rain_left_mm -= fall;
        *rain_mm = fall;
    }
}
