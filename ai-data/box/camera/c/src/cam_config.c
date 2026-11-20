#include "box_camera.h"

void cam_config_default(cam_config_t *c)
{
    c->min_mean = 15.0;
    c->min_std = 4.0;
    c->max_sat_frac = 0.5;
    c->min_grad = 1.0;
    c->warmup_frames = 3;
    c->frame_period_ms = 100;
    c->wifi_timeout_ms = 6000;
    c->post_timeout_ms = 8000;
    c->retry_delay_ms = 500;
    c->max_attempts = 2;
    c->session_budget_ms = 25000;
    c->upload_even_if_poor = false;
}
