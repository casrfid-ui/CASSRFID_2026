/* Stages 7c/7d: class wanted by the thresholds (with hysteresis), then debounce. */
#include "gc_internal.h"

int gc_wanted_class(double score, double depth_max, int peak_step, int current, const gc_config_t *cfg)
{
    bool in_event = current == GC_SMOKE || current == GC_DECOY;
    if (score >= cfg->smoke_on) {
        if (depth_max < 0.04 && in_event) return current;
        if (cfg->decoy_enabled && peak_step <= cfg->decoy_max_peak_step) return GC_DECOY;
        return GC_SMOKE;
    }
    if (score >= cfg->smoke_off && in_event) return current;
    return GC_NORMAL;
}

void gc_debounce(uint8_t *cls, uint8_t *cand, int *cand_n, int want, const gc_config_t *cfg)
{
    int need;
    if (want == *cls) { *cand = (uint8_t)want; *cand_n = 0; return; }
    *cand_n = (want == *cand) ? *cand_n + 1 : 1;
    *cand = (uint8_t)want;
    need = (want == GC_FAULT) ? 1 : (want == GC_NORMAL ? cfg->off_scans : cfg->on_scans);
    if (*cand_n >= need) { *cls = (uint8_t)want; *cand_n = 0; }
}
