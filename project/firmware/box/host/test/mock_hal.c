#include "mock_hal.h"

#include <stdio.h>
#include <string.h>

static mock_t *M(void *c) { return (mock_t *)c; }

static uint32_t h_now(void *c) { return M(c)->ms; }
static void h_delay(void *c, uint32_t ms) { M(c)->ms += ms; }
static int64_t h_rtc(void *c) { mock_t *m = M(c); return m->base_unix + m->rtc_offset_s + (int64_t)(m->ms / 1000); }
static void h_rtc_set(void *c, int64_t u) { mock_t *m = M(c); m->rtc_offset_s = u - m->base_unix - (int64_t)(m->ms / 1000); m->rtc_set = true; }
static uint32_t h_rand(void *c) { mock_t *m = M(c); m->rng = m->rng * 1664525u + 1013904223u; return m->rng >> 4; }
static bool h_env(void *c, double *t, double *rh) { mock_t *m = M(c); *t = m->env_t; *rh = m->env_rh; return m->env_ok; }
static void h_gas_power(void *c, bool on) { M(c)->gas_powered = on; }
static bool h_gas(void *c, double g[GC_NSTEP], double t[GC_NSTEP], double rh[GC_NSTEP])
{
    mock_t *m = M(c);
    int i;
    m->gas_calls++;
    for (i = 0; i < GC_NSTEP; i++) {
        g[i] = m->gas_base * (1.0 + 0.05 * i) * m->gas_scale * (1.0 + 0.002 * ((int)(m->gas_calls * 7 + i * 3) % 5 - 2));
        t[i] = m->env_t; rh[i] = m->env_rh;
    }
    return m->gas_ok;
}
static void h_flame(void *c, uint8_t raw[FL_MAX_SAMPLES], int n)
{
    mock_t *m = M(c);
    int i;
    m->flame_calls++;
    for (i = 0; i < n; i++) raw[i] = m->flame_on ? 0 : 1;           /* KY-026 is active low */
}
static int h_batt(void *c) { return M(c)->battery_pct; }
static bool h_batt_low(void *c) { return M(c)->battery_low; }
static bool h_hot(void *c) { return M(c)->housing_hot; }
static bool h_supply(void *c) { return M(c)->supply_fault; }
static void h_gps_power(void *c, bool on) { M(c)->gps_on = on; }
static bool h_gps_poll(void *c, ffp_pos_t *p, int64_t *u, uint32_t timeout)
{
    mock_t *m = M(c);
    (void)timeout;
    if (!m->gps_has_fix) return false;
    *p = m->gps_pos; *u = m->gps_unix;
    return true;
}
static void h_pump(void *c, bool on) { M(c)->pump_on = on; }
static void h_sleep(void *c, double s) { M(c)->ms += (uint32_t)(s * 1000.0); }

static void push_ack(mock_t *m, const ffp_frame_t *f, uint32_t at)
{
    ffp_frame_t a;
    ffp_ack_t k;
    k.acked_seq = f->seq; k.acked_type = f->type; k.flags = FFP_AF_SBC_UP; k.rssi_dbm = -90; k.snr_x4 = 20; k.gw_id = m->gw_id; k.alert_level = m->gw_alert_level;
    ffp_frame_init(&a, FFP_T_ACK, 0, m->gw_id, f->origin, 0);
    ffp_pack_ack(&a, &k);
    mock_inject(m, &a, at);
}

static int r_tx(void *c, const uint8_t w[FFP_FRAME_LEN])
{
    mock_t *m = M(c);
    ffp_frame_t f;
    if (m->n_tx < MOCK_TXLOG) { memcpy(m->tx_log[m->n_tx], w, FFP_FRAME_LEN); m->tx_ms[m->n_tx] = m->ms; }
    m->n_tx++;
    m->ms += 60;                                                     /* time on air */
    if (m->gw_auto_ack && !m->gw_dead && m->n_tx >= m->gw_ack_from_tx && ffp_decode(w, FFP_FRAME_LEN, &f) == 0 && (f.flags & FFP_F_ACK_REQ))
        push_ack(m, &f, m->ms + 80);
    return 0;
}

static int r_rx(void *c, uint8_t w[FFP_FRAME_LEN], int *rssi, int *snr, uint32_t timeout)
{
    mock_t *m = M(c);
    int best = -1, i;
    uint32_t deadline = m->ms + timeout;
    for (i = 0; i < MOCK_RXQ; i++)
        if (m->rxq[i].used && m->rxq[i].at_ms <= deadline && (best < 0 || m->rxq[i].at_ms < m->rxq[best].at_ms)) best = i;
    if (best < 0) { m->ms = deadline; return 0; }
    if (m->rxq[best].at_ms > m->ms) m->ms = m->rxq[best].at_ms;
    memcpy(w, m->rxq[best].w, FFP_FRAME_LEN);
    *rssi = m->rxq[best].rssi; *snr = 20;
    m->rxq[best].used = false;
    return 1;
}
static int r_sf(void *c, int sf) { M(c)->sf = sf; return 0; }

static int cam_power(void *c, bool on) { (void)c; (void)on; return 0; }
static int cam_luma(void *c, uint8_t *buf, size_t cap, int *w, int *h)
{
    int i;
    (void)c;
    *w = 80; *h = 60;
    if (cap < 4800) return -1;
    for (i = 0; i < 4800; i++) buf[i] = (uint8_t)(60 + (i * 37 + (i / 80) * 11) % 120);      /* textured: passes the quality check */
    return 0;
}
static int cam_jpeg(void *c, uint8_t *buf, size_t cap, size_t *len) { (void)c; if (cap < 64) return -1; memset(buf, 0xAB, 64); *len = 64; return 0; }
static int cam_wifi(void *c, bool on, uint32_t t) { (void)c; (void)on; (void)t; return 0; }
static int cam_post(void *c, const cam_request_t *rq, char *resp, size_t cap, uint32_t t, int *http)
{
    mock_t *m = M(c);
    (void)t;
    m->cam_runs++;
    m->cam_last_id = rq->ids.req_id;
    snprintf(resp, cap, "{\"v\":1,\"id\":%u,\"label\":\"%s\",\"conf\":%.3f,\"ms\":120}", (unsigned)rq->ids.req_id, m->cam_answer_label, m->cam_answer_conf);
    *http = 200;
    return 0;
}
static uint32_t cam_now(void *c) { return M(c)->ms; }
static void cam_delay(void *c, uint32_t ms) { M(c)->ms += ms; }
static const cam_hw_t *h_cam(void *c) { mock_t *m = M(c); return m->cam_present ? &m->cam : NULL; }

void mock_init(mock_t *m)
{
    memset(m, 0, sizeof *m);
    m->base_unix = 1793800000;            /* 4 Nov 2026 */
    m->gw_auto_ack = true; m->gw_ack_from_tx = 1; m->gw_id = 8;
    m->env_t = 28.0; m->env_rh = 40.0; m->env_ok = true; m->gas_ok = true; m->gas_base = 100000.0; m->gas_scale = 1.0;
    m->battery_pct = 80; m->rng = 12345;
    m->cam_present = true; m->cam_answer_label = "background"; m->cam_answer_conf = 0.95;
    m->cam.ctx = m; m->cam.power = cam_power; m->cam.grab_luma = cam_luma; m->cam.grab_jpeg = cam_jpeg; m->cam.wifi = cam_wifi;
    m->cam.post = cam_post; m->cam.now_ms = cam_now; m->cam.delay_ms = cam_delay;
    m->hal.ctx = m;
    m->hal.now_ms = h_now; m->hal.delay_ms = h_delay; m->hal.rtc_unix_s = h_rtc; m->hal.rtc_set_unix_s = h_rtc_set; m->hal.random32 = h_rand;
    m->hal.read_env = h_env; m->hal.gas_power = h_gas_power; m->hal.scan_gas = h_gas; m->hal.flame_burst = h_flame;
    m->hal.battery_pct = h_batt; m->hal.battery_low = h_batt_low; m->hal.housing_hot = h_hot; m->hal.supply_fault = h_supply;
    m->hal.gps_power = h_gps_power; m->hal.gps_poll = h_gps_poll; m->hal.pump = h_pump; m->hal.camera_hw = h_cam; m->hal.sleep_s = h_sleep;
    m->hal.radio.ctx = m; m->hal.radio.tx = r_tx; m->hal.radio.rx = r_rx; m->hal.radio.set_sf = r_sf;
}

void mock_inject(mock_t *m, const ffp_frame_t *f, uint32_t at_ms)
{
    int i;
    for (i = 0; i < MOCK_RXQ; i++)
        if (!m->rxq[i].used) { m->rxq[i].used = true; m->rxq[i].at_ms = at_ms; m->rxq[i].rssi = -95; ffp_encode(f, m->rxq[i].w); return; }
}

int mock_tx_decode(const mock_t *m, int i, ffp_frame_t *f)
{
    return ffp_decode(m->tx_log[i], FFP_FRAME_LEN, f);
}

int mock_count_tx(const mock_t *m, int type)
{
    int i, n = 0, lim = m->n_tx < MOCK_TXLOG ? m->n_tx : MOCK_TXLOG;
    for (i = 0; i < lim; i++) if ((m->tx_log[i][0] >> 4) == type) n++;
    return n;
}
