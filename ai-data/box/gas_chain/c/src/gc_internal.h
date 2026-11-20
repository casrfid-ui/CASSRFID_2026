/* One function per stage, same names and rules as python/src/gas_chain/stages.py. Exposed for the unit tests. */
#ifndef GC_INTERNAL_H
#define GC_INTERNAL_H
#include "gas_chain.h"

/* stage 2: quality (gc_quality.c) */
uint8_t gc_quality_flags(const double *gas, const double *temp, const double *rh, const double *prev_gas,
                         int *same_count, const gc_config_t *cfg);
/* stage 4: compensation (gc_compensate.c) */
void gc_compensate(const double *gas, const double *temp, const double *rh, const gc_config_t *cfg, double *out);
/* stage 3: filter (gc_filter.c) */
void gc_window_median(const double window[][GC_NSTEP], int filled, double *out);
bool gc_is_spike(const double *x, const double window[][GC_NSTEP], int filled, double spike_ln);
void gc_smooth(const double *previous, const double *value, double alpha, double *out);   /* previous NULL: first value */
/* stage 5: baseline (gc_baseline.c) */
bool gc_learning_gate(int scans, int filled, const gc_config_t *cfg);
bool gc_baseline_may_follow(int cls, double score, bool stuck, const gc_config_t *cfg);
void gc_baseline_follow(double *base, const double *ema, double dt_s, double tau_s);
/* stage 6 and 7a/7b: depth, bands, score (gc_score.c) */
void gc_band_depths(const double *depth, const gc_config_t *cfg, double *out);
double gc_instant_score(double depth_max, double depth_full);
double gc_update_cusum(double cusum, double depth_max, const gc_config_t *cfg);
/* stage 7c/7d: class (gc_class.c) */
int gc_wanted_class(double score, double depth_max, int peak_step, int current, const gc_config_t *cfg);
void gc_debounce(uint8_t *cls, uint8_t *cand, int *cand_n, int want, const gc_config_t *cfg);

#endif
