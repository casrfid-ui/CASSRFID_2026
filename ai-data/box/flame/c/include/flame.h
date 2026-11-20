/* Flame sensor processing of the box: a burst of digital reads of the KY-026 -> one yes / no per wake-up.
 * C99, no heap, no I/O, no global state. Reference: ../python (same results, tested by parity). */
#ifndef FLAME_H
#define FLAME_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define FL_MAX_SAMPLES 32            /* longest burst accepted */

typedef struct {
    bool active_low;                 /* KY-026 pulls DO low on flame (to check on the module) */
    int burst_samples;               /* reads per wake-up taken by the firmware (information for the firmware) */
    double vote_ratio;               /* share of positive reads that makes the burst positive */
    int flicker_min;                 /* minimum transitions for a positive burst; 0 = rule off */
} fl_config_t;

typedef struct {
    bool detected;
    double ratio;                    /* fraction of positive reads, 0..1 */
    int transitions;                 /* 0<->1 changes in the burst */
    int n;
} fl_result_t;

void fl_config_default(fl_config_t *cfg);

/* raw: n digital reads (0 or non-zero). Returns 0, or -1 for NULL pointers or n outside 1..FL_MAX_SAMPLES
 * (result untouched). cfg == NULL uses the defaults. */
int fl_process(const uint8_t *raw, int n, const fl_config_t *cfg, fl_result_t *out);

#ifdef __cplusplus
}
#endif
#endif
