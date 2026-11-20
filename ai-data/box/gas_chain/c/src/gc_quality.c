/* Stage 2: quality check. Range faults make the scan bad; identical scans in a row mean a stuck sensor. */
#include <math.h>
#include "gc_internal.h"

uint8_t gc_quality_flags(const double *gas, const double *temp, const double *rh, const double *prev_gas,
                         int *same_count, const gc_config_t *cfg)
{
    uint8_t faults = 0;
    bool out_of_range = false, identical = prev_gas != NULL;
    int i;
    for (i = 0; i < GC_NSTEP; i++) {
        /* NaN and infinity fail every comparison below, so they are tested on their own */
        if (!isfinite(gas[i]) || !isfinite(temp[i]) || !isfinite(rh[i])
            || gas[i] < cfg->gas_min_ohm || gas[i] > cfg->gas_max_ohm
            || temp[i] < cfg->temp_min_c || temp[i] > cfg->temp_max_c
            || rh[i] < 0.0 || rh[i] > 100.0)
            out_of_range = true;
        if (identical && !(gas[i] == prev_gas[i])) identical = false;
    }
    if (out_of_range) faults |= GC_F_RANGE;
    *same_count = identical ? *same_count + 1 : 0;
    if (*same_count >= cfg->stuck_scans) faults |= GC_F_STUCK;
    return faults;
}
