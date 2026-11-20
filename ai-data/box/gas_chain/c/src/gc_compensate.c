/* Stage 4: ln of the gas resistance with the linear temperature and humidity effect removed. */
#include <math.h>
#include "gc_internal.h"

void gc_compensate(const double *gas, const double *temp, const double *rh, const gc_config_t *cfg, double *out)
{
    int i;
    for (i = 0; i < GC_NSTEP; i++) {
        double t = temp[i] - cfg->t_offset_c;
        out[i] = log(gas[i]) - cfg->a_t * (t - 25.0) - cfg->b_h * (rh[i] - 50.0);
    }
}
