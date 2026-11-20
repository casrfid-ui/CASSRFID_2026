/* Stage 5: baseline of clean air. Built from the first scans after the burn-in, then follows slow drift in quiet air. */
#include <math.h>
#include "gc_internal.h"

bool gc_learning_gate(int scans, int filled, const gc_config_t *cfg)
{
    return scans > cfg->burnin_scans && filled >= cfg->median_window;
}

bool gc_baseline_may_follow(int cls, double score, bool stuck, const gc_config_t *cfg)
{
    return cls == GC_NORMAL && score < cfg->freeze_score && !stuck;
}

void gc_baseline_follow(double *base, const double *ema, double dt_s, double tau_s)
{
    double beta = 1.0 - exp(-dt_s / tau_s);
    int s;
    for (s = 0; s < GC_NSTEP; s++) base[s] = base[s] + beta * (ema[s] - base[s]);
}
