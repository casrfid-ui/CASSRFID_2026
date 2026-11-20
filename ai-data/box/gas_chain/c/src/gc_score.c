/* Stages 6 and 7a/7b: depth per band, instant score, CUSUM. */
#include "gc_internal.h"

void gc_band_depths(const double *depth, const gc_config_t *cfg, double *out)
{
    int b, i;
    for (b = 0; b < GC_NBANDS; b++) {
        double sum = 0.0;
        for (i = cfg->bands[b][0]; i < cfg->bands[b][1]; i++) sum += depth[i];
        out[b] = sum / (double)(cfg->bands[b][1] - cfg->bands[b][0]);
    }
}

double gc_instant_score(double depth_max, double depth_full)
{
    double s = depth_max / depth_full;
    return s < 0.0 ? 0.0 : (s > 1.0 ? 1.0 : s);
}

double gc_update_cusum(double cusum, double depth_max, const gc_config_t *cfg)
{
    double cap = 1.5 * cfg->cusum_h;
    if (depth_max > cfg->cusum_k) cusum += depth_max - cfg->cusum_k;
    else cusum *= 0.5;
    return cusum < cap ? cusum : cap;
}
