/* Gas chain of the box: one BME680 scan (10 heater steps) in, one score + class + flags out.
 * C99, no heap, no I/O, no global state: one gc_chain_t per sensor. Reference: ../python (same numbers).
 * Doubles are used on purpose: the chain runs once per 30 s to 300 s, so the soft double of the ESP32 costs nothing
 * that matters, and it keeps the C results equal to the Python reference to 1e-9. */
#ifndef GAS_CHAIN_H
#define GAS_CHAIN_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define GC_NSTEP 10             /* heater temperatures per scan */
#define GC_NBANDS 3             /* low, mid, high heater temperature */
#define GC_MEDIAN_MAX 9         /* upper bound of the median window (fixed-size buffer) */

enum { GC_NORMAL = 0, GC_SMOKE = 1, GC_DECOY = 2, GC_FAULT = 3 };
enum { GC_F_RANGE = 1, GC_F_STUCK = 2, GC_F_SPIKE = 4 };   /* GC_F_SPIKE is informational only */

typedef struct {
    /* quality */
    double gas_min_ohm, gas_max_ohm, temp_min_c, temp_max_c;
    int stuck_scans, bad_scans_to_fault;
    double spike_ln;
    /* filter */
    int median_window;
    double ema_alpha;
    /* compensation */
    double t_offset_c, a_t, b_h;
    /* baseline */
    int burnin_scans, warmup_scans;
    double tau_base_s, freeze_score;
    /* bands: [first, last) step of each band */
    int bands[GC_NBANDS][2];
    /* score and class */
    double depth_full, cusum_k, cusum_h, smoke_on, smoke_off;
    int on_scans, off_scans;
    bool decoy_enabled;
    int decoy_max_peak_step;
} gc_config_t;

typedef struct {
    double score;               /* 0..1 */
    uint8_t cls;                /* GC_NORMAL / GC_SMOKE / GC_DECOY / GC_FAULT */
    uint8_t faults;             /* GC_F_* bit mask */
    bool warmup;                /* baseline not ready: no class is trusted */
    bool scan_bad;              /* scan rejected by the quality check, state untouched */
    double depth;               /* largest band depth, ln units */
    int peak_step;              /* heater step with the largest depth */
    double bands[GC_NBANDS];    /* depth per band, ln units */
} gc_result_t;

typedef struct {
    gc_config_t cfg;
    int scans, same_count, bad_count;
    bool have_prev;
    double prev_gas[GC_NSTEP];
    double window[GC_MEDIAN_MAX][GC_NSTEP];
    int window_pos, window_filled;
    bool have_ema;
    double ema[GC_NSTEP];
    bool have_base;
    double base[GC_NSTEP];
    double warm_sum[GC_NSTEP];
    int warm_n;
    double cusum;
    uint8_t cls, cand;
    int cand_n;
} gc_chain_t;

/* Default tuning, identical to python/src/gas_chain/config.py. */
void gc_config_default(gc_config_t *cfg);

/* Returns 0, or -1 if the config is unusable (window size, band limits, thresholds, time constant). */
int gc_config_check(const gc_config_t *cfg);

/* cfg == NULL uses the defaults. Returns 0 or -1 (bad config; the chain is then unusable). */
int gc_init(gc_chain_t *c, const gc_config_t *cfg);

/* One scan. gas in ohm, temp in degC, rh in %, dt_s in seconds since the previous scan. Arrays hold GC_NSTEP values.
 * Inputs are not modified. Returns 0, or -1 on bad arguments (NULL pointer or dt_s not > 0), result untouched. */
int gc_update(gc_chain_t *c, const double *gas, const double *temp, const double *rh, double dt_s, gc_result_t *out);

/* Baseline persistence. snapshot: false while the baseline is not ready. restore: no burn-in, no warm-up. */
bool gc_snapshot(const gc_chain_t *c, double base[GC_NSTEP]);
void gc_restore(gc_chain_t *c, const double base[GC_NSTEP]);

#ifdef __cplusplus
}
#endif
#endif
