#include "nmea.h"

#include <ctype.h>
#include <stdlib.h>
#include <string.h>

int64_t nmea_days_from_civil(int y, unsigned m, unsigned d)
{
    int64_t era;
    unsigned yoe, doy, doe;
    y -= m <= 2;
    era = (y >= 0 ? y : y - 399) / 400;
    yoe = (unsigned)(y - era * 400);
    doy = (153u * (m + (m > 2 ? -3 : 9)) + 2u) / 5u + d - 1u;
    doe = yoe * 365u + yoe / 4u - yoe / 100u + doy;
    return era * 146097 + (int64_t)doe - 719468;
}

#define MAXF 20

static int split(char *s, char *f[], int max)
{
    int n = 0;
    f[n++] = s;
    while (*s && n < max) {
        if (*s == ',') { *s = 0; f[n++] = s + 1; }
        s++;
    }
    return n;
}

static int coord(const char *v, const char *hemi, int32_t *out)
{
    double x, deg;
    int i;
    if (!v[0] || !hemi[0]) return -1;
    for (i = 0; v[i]; i++) if (!isdigit((unsigned char)v[i]) && v[i] != '.') return -1;
    x = atof(v);                                  /* ddmm.mmmm or dddmm.mmmm */
    deg = (double)(int)(x / 100.0);
    x = deg + (x - deg * 100.0) / 60.0;
    if (hemi[0] == 'S' || hemi[0] == 'W') x = -x;
    else if (hemi[0] != 'N' && hemi[0] != 'E') return -1;
    *out = (int32_t)(x * 1e7 + (x >= 0 ? 0.5 : -0.5));
    return 0;
}

int nmea_feed(nmea_fix_t *fix, const char *line)
{
    char buf[128], *f[MAXF], *star;
    size_t n;
    int nf;
    uint8_t cs = 0;
    unsigned want;
    const char *p;

    if (!fix || !line || line[0] != '$') return -1;
    n = strlen(line);
    while (n && (line[n - 1] == '\r' || line[n - 1] == '\n')) n--;
    if (n < 8 || n >= sizeof buf) return -1;
    memcpy(buf, line, n);
    buf[n] = 0;
    star = strchr(buf, '*');
    if (star) {
        if (strlen(star) != 3) return -1;
        want = (unsigned)strtoul(star + 1, NULL, 16);
        for (p = buf + 1; p < star; p++) cs ^= (uint8_t)*p;
        if (cs != want) return -1;
        *star = 0;
    }
    nf = split(buf + 1, f, MAXF);
    if (nf < 7 || strlen(f[0]) != 5) return -1;
    if (strcmp(f[0] + 2, "GGA") == 0 && nf >= 10) {
        int q = atoi(f[6]);
        int32_t la, lo;
        if (q <= 0) return 0;
        if (coord(f[2], f[3], &la) || coord(f[4], f[5], &lo)) return -1;
        fix->lat_e7 = la; fix->lon_e7 = lo;
        fix->sats = (uint8_t)atoi(f[7]);
        fix->alt_m = (int16_t)atof(f[9]);
        fix->have_pos = true;
        return 1;
    }
    if (strcmp(f[0] + 2, "RMC") == 0 && nf >= 10) {
        int hh, mm, ss, dd, mo, yy;
        if (f[2][0] != 'A' || strlen(f[1]) < 6 || strlen(f[9]) != 6) return 0;
        hh = (f[1][0] - '0') * 10 + (f[1][1] - '0'); mm = (f[1][2] - '0') * 10 + (f[1][3] - '0'); ss = (f[1][4] - '0') * 10 + (f[1][5] - '0');
        dd = (f[9][0] - '0') * 10 + (f[9][1] - '0'); mo = (f[9][2] - '0') * 10 + (f[9][3] - '0'); yy = 2000 + (f[9][4] - '0') * 10 + (f[9][5] - '0');
        if (hh > 23 || mm > 59 || ss > 60 || dd < 1 || dd > 31 || mo < 1 || mo > 12) return -1;
        fix->unix_s = nmea_days_from_civil(yy, (unsigned)mo, (unsigned)dd) * 86400 + hh * 3600 + mm * 60 + ss;
        fix->have_time = true;
        return 1;
    }
    return 0;
}
