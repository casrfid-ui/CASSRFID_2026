#include "flame.h"

void fl_config_default(fl_config_t *c)
{
    c->active_low = true;
    c->burst_samples = 8;
    c->vote_ratio = 0.625;
    c->flicker_min = 0;
}

int fl_process(const uint8_t *raw, int n, const fl_config_t *cfg, fl_result_t *out)
{
    fl_config_t d;
    int i, positives = 0, flicker = 0;
    bool prev = false, vote;

    if (!raw || !out || n < 1 || n > FL_MAX_SAMPLES) return -1;
    if (!cfg) { fl_config_default(&d); cfg = &d; }
    for (i = 0; i < n; i++) {
        bool a = cfg->active_low ? (raw[i] == 0) : (raw[i] != 0);      /* stage 1: polarity */
        if (a) positives++;
        if (i > 0 && a != prev) flicker++;                            /* stage 3: transitions */
        prev = a;
    }
    vote = (double)positives >= cfg->vote_ratio * (double)n;           /* stage 2: vote */
    out->detected = vote && flicker >= cfg->flicker_min;
    out->ratio = (double)positives / (double)n;
    out->transitions = flicker;
    out->n = n;
    return 0;
}
