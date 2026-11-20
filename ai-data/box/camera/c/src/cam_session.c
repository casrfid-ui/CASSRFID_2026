/* One capture-and-send session. Every exit goes through `finish`, which powers the camera and Wi-Fi off. */
#include <string.h>
#include "box_camera.h"

typedef struct {
    const cam_hw_t *hw;
    uint32_t t0;
    uint32_t budget;
    bool power_on, wifi_on;
} sess_t;

static uint32_t elapsed(const sess_t *s) { return (uint32_t)(s->hw->now_ms(s->hw->ctx) - s->t0); }
static bool out_of_time(const sess_t *s) { return elapsed(s) >= s->budget; }

static void finish(sess_t *s, cam_result_t *out, uint8_t status)
{
    if (s->wifi_on) { s->hw->wifi(s->hw->ctx, false, 0); s->wifi_on = false; }
    if (s->power_on) { s->hw->power(s->hw->ctx, false); s->power_on = false; }
    out->status = status;
    out->valid = (status == CAM_OK);
    out->elapsed_ms = elapsed(s);
}

int cam_session_run(const cam_hw_t *hw, const cam_config_t *cfg, const cam_ids_t *ids, cam_workspace_t *ws,
                    uint8_t *jpeg, size_t jpeg_cap, cam_result_t *out)
{
    sess_t s;
    cam_request_t rq;
    size_t jlen = 0;
    int w = 0, h = 0, i, attempt, http = 0, rc;
    uint8_t status = CAM_E_HTTP;

    if (!out) return -1;
    memset(out, 0, sizeof *out);
    out->model_ms = -1;
    if (!hw || !cfg || !ids || !ws || !jpeg || jpeg_cap == 0 || !hw->power || !hw->grab_luma || !hw->grab_jpeg
        || !hw->wifi || !hw->post || !hw->now_ms || !hw->delay_ms || cfg->max_attempts < 1) {
        out->status = CAM_E_ARG;
        return -1;
    }
    s.hw = hw; s.power_on = false; s.wifi_on = false; s.budget = cfg->session_budget_ms;
    s.t0 = hw->now_ms(hw->ctx);

    /* 1. power on */
    if (hw->power(hw->ctx, true) != 0) { finish(&s, out, CAM_E_POWER); return 0; }
    s.power_on = true;

    /* 2. warm-up: grab and discard */
    for (i = 0; i < cfg->warmup_frames; i++) {
        if (out_of_time(&s)) { finish(&s, out, CAM_E_TIMEOUT); return 0; }
        if (hw->grab_luma(hw->ctx, ws->luma, sizeof ws->luma, &w, &h) != 0) { finish(&s, out, CAM_E_CAPTURE); return 0; }
        hw->delay_ms(hw->ctx, cfg->frame_period_ms);
    }

    /* 3. quality check on one more grayscale frame */
    if (out_of_time(&s)) { finish(&s, out, CAM_E_TIMEOUT); return 0; }
    if (hw->grab_luma(hw->ctx, ws->luma, sizeof ws->luma, &w, &h) != 0
        || cam_quality(ws->luma, w, h, cfg, &out->quality) != 0) { finish(&s, out, CAM_E_CAPTURE); return 0; }
    if (out->quality.flags != 0 && !cfg->upload_even_if_poor) { finish(&s, out, CAM_E_QUALITY); return 0; }

    /* 4. JPEG */
    if (hw->grab_jpeg(hw->ctx, jpeg, jpeg_cap, &jlen) != 0 || jlen == 0 || jlen > jpeg_cap) {
        finish(&s, out, CAM_E_CAPTURE);
        return 0;
    }

    /* 5. Wi-Fi */
    if (out_of_time(&s)) { finish(&s, out, CAM_E_TIMEOUT); return 0; }
    s.wifi_on = true;                                      /* switched off by finish even if the connection fails half way */
    if (hw->wifi(hw->ctx, true, cfg->wifi_timeout_ms) != 0) { finish(&s, out, CAM_E_WIFI); return 0; }

    /* 6. send, with retries inside the budget */
    memset(&rq, 0, sizeof rq);
    rq.ids = *ids; rq.jpeg = jpeg; rq.jpeg_len = jlen;
    if (cam_build_headers(rq.headers, sizeof rq.headers, ids) < 0) { finish(&s, out, CAM_E_ARG); return 0; }
    for (attempt = 0; attempt < cfg->max_attempts; attempt++) {
        uint32_t left, tmo;
        uint8_t label = 0;
        double conf = 0.0;
        int model_ms = -1;

        if (out_of_time(&s)) { status = CAM_E_TIMEOUT; break; }
        left = s.budget - elapsed(&s);
        tmo = cfg->post_timeout_ms < left ? cfg->post_timeout_ms : left;
        ws->resp[0] = '\0';
        http = 0;
        out->attempts = attempt + 1;
        rc = hw->post(hw->ctx, &rq, ws->resp, sizeof ws->resp, tmo, &http);
        out->http_status = http;
        ws->resp[sizeof ws->resp - 1] = '\0';
        if (rc != 0 || http != 200) {
            status = CAM_E_HTTP;
        } else {
            rc = cam_parse_response(ws->resp, ids->req_id, &label, &conf, &model_ms);
            if (rc == 0) {
                out->label = label; out->conf = conf; out->model_ms = model_ms;
                status = CAM_OK;
                break;
            }
            status = CAM_E_RESPONSE;
        }
        if (attempt + 1 < cfg->max_attempts) hw->delay_ms(hw->ctx, cfg->retry_delay_ms);
    }
    finish(&s, out, status);
    return 0;
}
