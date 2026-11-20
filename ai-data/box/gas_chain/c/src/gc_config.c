#include <math.h>
#include "gas_chain.h"

void gc_config_default(gc_config_t *c)
{
    c->gas_min_ohm = 1000.0;
    c->gas_max_ohm = 120000000.0;   /* BME688 saturates at 102.4 Mohm: a valid reading */
    c->temp_min_c = -40.0;
    c->temp_max_c = 85.0;
    c->stuck_scans = 12;
    c->bad_scans_to_fault = 3;
    c->spike_ln = 1.5;
    c->median_window = 5;
    c->ema_alpha = 0.35;
    c->t_offset_c = 0.0;
    c->a_t = 0.0;
    c->b_h = 0.0;
    c->burnin_scans = 6;
    c->warmup_scans = 6;
    c->tau_base_s = 6.0 * 3600.0;
    c->freeze_score = 0.10;
    c->bands[0][0] = 0; c->bands[0][1] = 4;
    c->bands[1][0] = 4; c->bands[1][1] = 7;
    c->bands[2][0] = 7; c->bands[2][1] = 10;
    c->depth_full = 0.30;
    c->cusum_k = 0.03;
    c->cusum_h = 1.0;
    c->smoke_on = 0.40;
    c->smoke_off = 0.20;
    c->on_scans = 2;
    c->off_scans = 3;
    c->decoy_enabled = false;
    c->decoy_max_peak_step = 2;
}

int gc_config_check(const gc_config_t *c)
{
    int i;
    if (!c) return -1;
    if (c->median_window < 1 || c->median_window > GC_MEDIAN_MAX) return -1;
    if (!(c->ema_alpha > 0.0 && c->ema_alpha <= 1.0)) return -1;
    if (!(c->tau_base_s > 0.0) || !(c->depth_full > 0.0) || !(c->cusum_h > 0.0)) return -1;
    if (!(c->gas_min_ohm > 0.0) || !(c->gas_max_ohm > c->gas_min_ohm)) return -1;
    if (!(c->smoke_off <= c->smoke_on)) return -1;
    if (c->stuck_scans < 1 || c->bad_scans_to_fault < 1 || c->on_scans < 1 || c->off_scans < 1) return -1;
    if (c->burnin_scans < 0 || c->warmup_scans < 1) return -1;
    for (i = 0; i < GC_NBANDS; i++)
        if (c->bands[i][0] < 0 || c->bands[i][1] > GC_NSTEP || c->bands[i][0] >= c->bands[i][1]) return -1;
    if (isnan(c->a_t) || isnan(c->b_h) || isnan(c->t_offset_c)) return -1;
    return 0;
}
