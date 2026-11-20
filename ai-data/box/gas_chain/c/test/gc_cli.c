/* Parity tool: reads scans on stdin, one per line: 30 numbers (gas[10] temp[10] rh[10]) then dt_s.
 * A line "R b0 ... b9" restores a baseline. Prints one line per scan:
 *   score cls faults warmup scan_bad depth peak b0 b1 b2   (numbers with 17 significant digits) */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "gas_chain.h"

int main(void)
{
    static char line[8192];
    gc_chain_t c;
    if (gc_init(&c, NULL) != 0) return 2;
    while (fgets(line, sizeof line, stdin)) {
        double v[GC_NSTEP * 3 + 1];
        gc_result_t r;
        char *p = line, *end;
        int n;
        if (line[0] == 'R') {
            for (n = 0, p = line + 1; n < GC_NSTEP; n++) { v[n] = strtod(p, &end); p = end; }
            gc_restore(&c, v);
            continue;
        }
        for (n = 0; n < GC_NSTEP * 3 + 1; n++) { v[n] = strtod(p, &end); if (end == p) return 3; p = end; }
        if (gc_update(&c, v, v + GC_NSTEP, v + 2 * GC_NSTEP, v[3 * GC_NSTEP], &r) != 0) return 4;
        printf("%.17g %d %d %d %d %.17g %d %.17g %.17g %.17g\n", r.score, r.cls, r.faults, r.warmup, r.scan_bad,
               r.depth, r.peak_step, r.bands[0], r.bands[1], r.bands[2]);
    }
    return 0;
}
