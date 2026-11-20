/* Orchestrator: same order as python/src/gas_chain/chain.py. */
#include <math.h>
#include <string.h>
#include "gc_internal.h"

int gc_init(gc_chain_t *c, const gc_config_t *cfg)
{
    gc_config_t d;
    if (!c) return -1;
    memset(c, 0, sizeof *c);
    if (!cfg) { gc_config_default(&d); cfg = &d; }
    c->cfg = *cfg;
    c->cls = c->cand = GC_NORMAL;
    return gc_config_check(&c->cfg);
}

bool gc_snapshot(const gc_chain_t *c, double base[GC_NSTEP])
{
    if (!c->have_base) return false;
    memcpy(base, c->base, sizeof c->base);
    return true;
}

void gc_restore(gc_chain_t *c, const double base[GC_NSTEP])
{
    memcpy(c->base, base, sizeof c->base);
    c->have_base = true;
    c->warm_n = c->cfg.warmup_scans;
}

static void learn_baseline(gc_chain_t *c)
{
    int s;
    if (!gc_learning_gate(c->scans, c->window_filled, &c->cfg)) return;
    for (s = 0; s < GC_NSTEP; s++) c->warm_sum[s] += c->ema[s];
    c->warm_n++;
    if (c->warm_n == c->cfg.warmup_scans) {
        for (s = 0; s < GC_NSTEP; s++) c->base[s] = c->warm_sum[s] / (double)c->warm_n;
        c->have_base = true;
    }
}

int gc_update(gc_chain_t *c, const double *gas, const double *temp, const double *rh, double dt_s, gc_result_t *out)
{
    const gc_config_t *cfg;
    gc_result_t r;
    double x[GC_NSTEP], med[GC_NSTEP], depth[GC_NSTEP], depth_max, inst, cum, score;
    uint8_t faults;
    bool stuck;
    int s, peak, want;

    if (!c || !gas || !temp || !rh || !out || !(dt_s > 0.0) || !isfinite(dt_s)) return -1;
    cfg = &c->cfg;
    memset(&r, 0, sizeof r);
    r.cls = GC_NORMAL;
    r.warmup = true;

    faults = gc_quality_flags(gas, temp, rh, c->have_prev ? c->prev_gas : NULL, &c->same_count, cfg);
    memcpy(c->prev_gas, gas, sizeof c->prev_gas);
    c->have_prev = true;

    if (faults & GC_F_RANGE) {                    /* a bad scan never enters the state */
        c->bad_count++;
        r.scan_bad = true;
        r.faults = faults;
        r.warmup = !c->have_base;
        if (c->bad_count >= cfg->bad_scans_to_fault) c->cls = GC_FAULT;
        r.cls = c->cls;
        *out = r;
        return 0;
    }
    c->bad_count = 0;
    c->scans++;

    gc_compensate(gas, temp, rh, cfg, x);
    if (gc_is_spike(x, (const double (*)[GC_NSTEP])c->window, c->window_filled, cfg->spike_ln)) faults |= GC_F_SPIKE;
    memcpy(c->window[c->window_pos], x, sizeof x);
    c->window_pos = (c->window_pos + 1) % cfg->median_window;
    if (c->window_filled < cfg->median_window) c->window_filled++;
    gc_window_median((const double (*)[GC_NSTEP])c->window, c->window_filled, med);
    gc_smooth(c->have_ema ? c->ema : NULL, med, cfg->ema_alpha, c->ema);
    c->have_ema = true;
    stuck = (faults & GC_F_STUCK) != 0;

    if (!c->have_base || c->warm_n < cfg->warmup_scans) {
        learn_baseline(c);
        r.faults = faults;
        r.cls = stuck ? GC_FAULT : c->cls;
        *out = r;
        return 0;
    }

    for (s = 0; s < GC_NSTEP; s++) depth[s] = c->base[s] - c->ema[s];   /* resistance drops in smoke: depth > 0 */
    gc_band_depths(depth, cfg, r.bands);
    depth_max = r.bands[0];
    for (s = 1; s < GC_NBANDS; s++) if (r.bands[s] > depth_max) depth_max = r.bands[s];
    if (depth_max < 0.0) depth_max = 0.0;
    c->cusum = gc_update_cusum(c->cusum, depth_max, cfg);
    inst = gc_instant_score(depth_max, cfg->depth_full);
    cum = c->cusum / cfg->cusum_h;
    cum = cum < 0.0 ? 0.0 : (cum > 1.0 ? 1.0 : cum);
    score = inst > cum ? inst : cum;
    peak = 0;
    for (s = 1; s < GC_NSTEP; s++) if (depth[s] > depth[peak]) peak = s;

    want = stuck ? GC_FAULT : gc_wanted_class(score, depth_max, peak, c->cls, cfg);
    gc_debounce(&c->cls, &c->cand, &c->cand_n, want, cfg);

    if (gc_baseline_may_follow(c->cls, score, stuck, cfg)) gc_baseline_follow(c->base, c->ema, dt_s, cfg->tau_base_s);

    r.score = score;
    r.cls = c->cls;
    r.faults = faults;
    r.warmup = false;
    r.depth = depth_max;
    r.peak_step = peak;
    *out = r;
    return 0;
}
