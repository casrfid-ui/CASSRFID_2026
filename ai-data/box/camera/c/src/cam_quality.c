/* Image quality of a small grayscale frame. Integer sums, so the result equals the Python reference exactly. */
#include <math.h>
#include "box_camera.h"

int cam_quality(const uint8_t *luma, int w, int h, const cam_config_t *cfg, cam_quality_t *out)
{
    long n, x, y, npairs;
    unsigned long long sum = 0, sumsq = 0, grad_sum = 0;
    long sat = 0, dark = 0;
    double mean, var;
    uint8_t flags = 0;

    if (!luma || !cfg || !out || w < 2 || h < 2 || (long)w * (long)h > CAM_LUMA_MAX) return -1;
    n = (long)w * (long)h;
    for (y = 0; y < h; y++) {
        const uint8_t *row = luma + y * w;
        for (x = 0; x < w; x++) {
            unsigned v = row[x];
            sum += v;
            sumsq += (unsigned long long)v * v;
            if (v >= 250) sat++;
            if (v <= 5) dark++;
            if (x + 1 < w) grad_sum += (unsigned)(v > row[x + 1] ? v - row[x + 1] : row[x + 1] - v);
            if (y + 1 < h) { unsigned u = row[x + w]; grad_sum += (unsigned)(v > u ? v - u : u - v); }
        }
    }
    npairs = (long)(w - 1) * h + (long)w * (h - 1);
    mean = (double)sum / (double)n;
    var = (double)sumsq / (double)n - mean * mean;
    if (var < 0.0) var = 0.0;
    out->mean = mean;
    out->std = sqrt(var);
    out->sat_frac = (double)sat / (double)n;
    out->dark_frac = (double)dark / (double)n;
    out->grad = (double)grad_sum / (double)npairs;
    if (out->mean < cfg->min_mean) flags |= CAM_Q_DARK;
    if (out->std < cfg->min_std) flags |= CAM_Q_BLOCKED;
    if (out->sat_frac > cfg->max_sat_frac) flags |= CAM_Q_SATURATED;
    if (out->grad < cfg->min_grad && out->std >= cfg->min_std) flags |= CAM_Q_BLURRY;
    out->flags = flags;
    return 0;
}
