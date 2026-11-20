/* Parity tool: one burst per line: active_low vote_ratio flicker_min n r0 ... r(n-1).
 * Prints: detected ratio transitions n  (or "ERR" when the burst is refused) */
#include <stdio.h>
#include <stdlib.h>
#include "flame.h"

int main(void)
{
    static char line[1024];
    while (fgets(line, sizeof line, stdin)) {
        fl_config_t cfg;
        fl_result_t r;
        uint8_t raw[FL_MAX_SAMPLES];
        char *p = line, *e;
        int n, i;
        fl_config_default(&cfg);
        cfg.active_low = strtol(p, &e, 10) != 0; p = e;
        cfg.vote_ratio = strtod(p, &e); p = e;
        cfg.flicker_min = (int)strtol(p, &e, 10); p = e;
        n = (int)strtol(p, &e, 10); p = e;
        for (i = 0; i < n && i < FL_MAX_SAMPLES; i++) { raw[i] = (uint8_t)strtol(p, &e, 10); p = e; }
        if (fl_process(raw, n, &cfg, &r) != 0) { printf("ERR\n"); continue; }
        printf("%d %.17g %d %d\n", r.detected, r.ratio, r.transitions, r.n);
    }
    return 0;
}
