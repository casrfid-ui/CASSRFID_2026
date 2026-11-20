/* Host tool used by the parity tests against the Python reference.
 *   fwi_cli hourly [state_file]   stdin: "hour month temp rh wind rain" per line
 *   fwi_cli daily [f0 p0 d0]      stdin: "temp rh wind rain month" per line (xclim-style daily chain)
 * Output: one line per input, full precision. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "fwi.h"

static int file_read(void *ctx, uint8_t *buf, size_t len)
{
    FILE *f = fopen((const char *)ctx, "rb");
    size_t n;
    if (!f) return -1;
    n = fread(buf, 1, len, f);
    fclose(f);
    return (int)n;
}

static int file_write(void *ctx, const uint8_t *buf, size_t len)
{
    FILE *f = fopen((const char *)ctx, "wb");
    if (!f) return -1;
    if (fwrite(buf, 1, len, f) != len) { fclose(f); return -1; }
    fclose(f);
    return 0;
}

static int run_hourly(const char *state_file)
{
    fwi_engine_t e;
    fwi_storage_t st;
    fwi_input_t in;
    fwi_output_t out;
    char line[256];
    if (state_file) {
        st.read = file_read; st.write = file_write; st.ctx = (void *)state_file;
        fwi_engine_init(&e, &st, NULL, NULL);
    } else {
        fwi_engine_init(&e, NULL, NULL, NULL);
    }
    while (fgets(line, sizeof line, stdin)) {
        if (sscanf(line, "%d %d %lf %lf %lf %lf", &in.hour, &in.month, &in.temp_c, &in.rh_pct, &in.wind_kmh, &in.rain_mm) != 6)
            continue;
        if (fwi_engine_update_hour(&e, &in, &out) != FWI_OK) { puts("ERR"); continue; }
        printf("%.17g %.17g %.17g %.17g %.17g %.17g %d %d %d %d\n", out.ffmc, out.dmc, out.dc, out.isi, out.bui, out.fwi,
               out.danger, (int)out.mode, out.history_hours, out.provisional);
    }
    return 0;
}

static int run_daily(double f, double p, double d)
{
    char line[256];
    double t, h, w, r;
    int m;
    while (fgets(line, sizeof line, stdin)) {
        double i, b;
        if (sscanf(line, "%lf %lf %lf %lf %d", &t, &h, &w, &r, &m) != 5) continue;
        f = fwi_ffmc_daily(f, t, h, w, r);
        p = fwi_dmc(p, t, h, r, m, fwi_le_46n);
        d = fwi_dc(d, t, r, m, fwi_lf_46n);
        i = fwi_isi(f, w);
        b = fwi_bui(p, d);
        printf("%.17g %.17g %.17g %.17g %.17g %.17g\n", f, p, d, i, b, fwi_fwi(i, b));
    }
    return 0;
}

int main(int argc, char **argv)
{
    if (argc >= 2 && strcmp(argv[1], "hourly") == 0) return run_hourly(argc >= 3 ? argv[2] : NULL);
    if (argc >= 2 && strcmp(argv[1], "daily") == 0)
        return run_daily(argc >= 5 ? atof(argv[2]) : FWI_DEFAULT_FFMC, argc >= 5 ? atof(argv[3]) : FWI_DEFAULT_DMC,
                         argc >= 5 ? atof(argv[4]) : FWI_DEFAULT_DC);
    fprintf(stderr, "usage: fwi_cli hourly [state_file] | fwi_cli daily [f0 p0 d0]\n");
    return 2;
}
