/* Parity tool. argv[1] = UTC offset in seconds. One tick per line:
 *   unix weather_valid temp rh wind rain gas_valid g[10] t[10] h[10] flame cam_valid cam_label cam_conf battery housing supply [n r0 ... r(n-1)]
 * Prints: state interval cam gps act reasons gasp nframes (kind rep)* | fwi_updated danger mode fwi ffmc dmc dc | scanned cls score warmup */
#include <stdio.h>
#include <stdlib.h>
#include "box_runtime.h"

int main(int argc, char **argv)
{
    static char line[16384];
    box_runtime_t rt;
    box_config_t cfg;
    box_config_default(&cfg);
    cfg.utc_offset_s = argc > 1 ? atoi(argv[1]) : 0;
    if (box_runtime_init(&rt, &cfg, NULL) < 0) return 2;
    while (fgets(line, sizeof line, stdin)) {
        box_tick_t t = {0};
        box_output_t o;
        char *p = line, *e;
        int i, k;
        long long unix_s = strtoll(p, &e, 10); p = e;
        t.unix_s = unix_s;
        t.weather_valid = (int)strtol(p, &e, 10) != 0; p = e;
        t.temp_c = strtod(p, &e); p = e;
        t.rh_pct = strtod(p, &e); p = e;
        t.wind_kmh = strtod(p, &e); p = e;
        t.rain_mm = strtod(p, &e); p = e;
        t.gas_valid = (int)strtol(p, &e, 10) != 0; p = e;
        for (i = 0; i < GC_NSTEP; i++) { t.gas_ohm[i] = strtod(p, &e); p = e; }
        for (i = 0; i < GC_NSTEP; i++) { t.gas_temp_c[i] = strtod(p, &e); p = e; }
        for (i = 0; i < GC_NSTEP; i++) { t.gas_rh_pct[i] = strtod(p, &e); p = e; }
        t.flame = (int)strtol(p, &e, 10) != 0; p = e;
        t.camera_valid = (int)strtol(p, &e, 10) != 0; p = e;
        t.camera_label = (uint8_t)strtol(p, &e, 10); p = e;
        t.camera_conf = strtod(p, &e); p = e;
        t.battery_low = (int)strtol(p, &e, 10) != 0; p = e;
        t.housing_hot = (int)strtol(p, &e, 10) != 0; p = e;
        t.supply_fault = (int)strtol(p, &e, 10) != 0; p = e;
        { long fn = strtol(p, &e, 10);                /* optional trailing burst: n r0 ... r(n-1) */
          if (e != p && fn > 0 && fn <= FL_MAX_SAMPLES) {
              p = e;
              t.flame_n = (uint8_t)fn;
              for (i = 0; i < fn; i++) { t.flame_raw[i] = (uint8_t)strtol(p, &e, 10); p = e; }
          } }
        if (box_runtime_step(&rt, &t, &o) != 0) return 4;
        printf("%d %.17g %d %d %d %d %d %d", o.sm.state, o.sm.interval_s, o.sm.camera_on, o.sm.gps_on, o.sm.actuator,
               o.sm.reasons, o.sm.last_gasp, o.sm.n_frames);
        for (k = 0; k < o.sm.n_frames; k++) printf(" %d %d", o.sm.frames[k].kind, o.sm.frames[k].repeats);
        printf(" | %d %d %d %.17g %.17g %.17g %.17g", o.fwi_updated, o.fwi.danger, o.fwi.mode, o.fwi.fwi, o.fwi.ffmc,
               o.fwi.dmc, o.fwi.dc);
        printf(" | %d %d %.17g %d\n", o.gas_scanned, o.gas.cls, o.gas.score, o.gas.warmup);
    }
    return 0;
}
