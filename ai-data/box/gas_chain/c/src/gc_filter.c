/* Stage 3: median of the last scans per heater step, then exponential smoothing. Also the informational spike flag. */
#include <math.h>
#include "gc_internal.h"

void gc_window_median(const double window[][GC_NSTEP], int filled, double *out)
{
    int s, i, j;
    for (s = 0; s < GC_NSTEP; s++) {
        double v[GC_MEDIAN_MAX];
        for (i = 0; i < filled; i++) {          /* insertion sort of the column */
            double x = window[i][s];
            for (j = i; j > 0 && v[j - 1] > x; j--) v[j] = v[j - 1];
            v[j] = x;
        }
        out[s] = (filled % 2) ? v[filled / 2] : (v[filled / 2 - 1] + v[filled / 2]) / 2.0;
    }
}

bool gc_is_spike(const double *x, const double window[][GC_NSTEP], int filled, double spike_ln)
{
    double med[GC_NSTEP];
    int s;
    if (filled <= 0) return false;
    gc_window_median(window, filled, med);
    for (s = 0; s < GC_NSTEP; s++)
        if (fabs(x[s] - med[s]) > spike_ln) return true;
    return false;
}

void gc_smooth(const double *previous, const double *value, double alpha, double *out)
{
    int s;
    for (s = 0; s < GC_NSTEP; s++)
        out[s] = previous ? previous[s] + alpha * (value[s] - previous[s]) : value[s];
}
