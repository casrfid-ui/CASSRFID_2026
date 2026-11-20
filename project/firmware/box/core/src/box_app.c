#include "box_app.h"

#include <math.h>
#include <string.h>

static const uint8_t SM_TO_FFP[5] = { 0, FFP_T_ALERT, FFP_T_STATE, FFP_T_HEARTBEAT, FFP_T_LAST_GASP };

void box_app_cfg_default(box_app_cfg_t *c, uint8_t box_id, uint8_t other_id)
{
    memset(c, 0, sizeof *c);
    c->box_id = box_id;
    c->other_id = other_id;
    box_config_default(&c->rt);
    box_link_cfg_default(&c->link);
    c->gps_boot_timeout_ms = 90000;
    c->gps_alert_timeout_ms = 1500;
    c->rx_window_ms = 1500;
    c->alert_listen_s = 20.0;
    c->pos_period_s = 6.0 * 3600.0;
    c->force_alert_default_ttl_s = 3600.0;
    c->default_sf = 9;
}

void box_retained_init(box_retained_t *r, uint32_t seed)
{
    memset(r, 0, sizeof *r);
    r->magic = BOX_RET_MAGIC;
    box_link_state_init(&r->link);
    box_wxsim_init(&r->wx, seed);
}

int box_app_init(box_app_t *a, const box_app_cfg_t *cfg, const box_hal_t *hal, box_retained_t *ret, const box_kv_t *kv)
{
    if (!a || !cfg || !hal || !ret) return -1;
    a->cfg = *cfg;
    a->hal = hal;
    a->ret = ret;
    if (ret->magic != BOX_RET_MAGIC) box_retained_init(ret, hal->random32 ? hal->random32(hal->ctx) : 1u);
    if (ret->sf < 7 || ret->sf > 12) ret->sf = cfg->default_sf;
    a->restored_mask = box_runtime_init(&a->rt, &a->cfg.rt, kv);
    if (a->restored_mask < 0) return -1;
    box_link_init(&a->link, &a->cfg.link, &ret->link, hal, cfg->box_id, cfg->other_id);
    if (hal->radio.set_sf) hal->radio.set_sf(hal->radio.ctx, ret->sf);
    memset(&a->last_tick, 0, sizeof a->last_tick);
    memset(&a->last_out, 0, sizeof a->last_out);
    return 0;
}

static double clampd(double x, double lo, double hi) { return x < lo ? lo : x > hi ? hi : x; }

static void apply_downlink(box_app_t *a, const box_downlinks_t *dl, int64_t now)
{
    box_retained_t *r = a->ret;
    uint8_t i;
    for (i = 0; i < dl->n; i++) {
        const box_downlink_t *d = &dl->items[i];
        if (d->kind == FFP_T_ACK) {
            r->gw_alert_level = d->ack.alert_level;
            if ((d->ack.flags & FFP_AF_OPERATOR) && d->ack.acked_type != 0) box_runtime_reset_fire(&a->rt);
        } else if (d->kind == FFP_T_TIME) {
            if (d->time.unix_s > 1700000000u) {                 /* later than Nov 2023: refuse a nonsense value */
                a->hal->rtc_set_unix_s(a->hal->ctx, (int64_t)d->time.unix_s);
                r->clock_synced = true;
                a->rt.cfg.utc_offset_s = (int32_t)d->time.utc_offset_q * 900;
            }
        } else if (d->kind == FFP_T_CMD) {
            const uint8_t *g = d->cmd.arg;
            switch (d->cmd.id) {
            case FFP_C_SET_THRESH: {
                /* bounded: the gateway can tune the thresholds, not switch the detection off */
                double on = clampd(g[0] / 100.0, 0.25, 0.80), off = clampd(g[1] / 100.0, 0.10, 0.60), cam = clampd(g[2] / 100.0, 0.40, 0.90);
                if (off > on) off = on;
                a->rt.gas.cfg.smoke_on = on; a->rt.gas.cfg.smoke_off = off;
                a->rt.sm.cfg.camera_confidence = cam;
                break;
            }
            case FFP_C_RISK_PRIOR:
                if (g[1] >= 2) r->force_alert_until_unix = now + (g[2] ? (int64_t)g[2] * 600 : (int64_t)a->cfg.force_alert_default_ttl_s);
                break;
            case FFP_C_FORCE_MODE:       /* raise only: the box never goes below what its own FWI decides */
                if (g[0] == 2) r->force_alert_until_unix = now + (g[1] ? (int64_t)g[1] * 600 : (int64_t)a->cfg.force_alert_default_ttl_s);
                break;
            case FFP_C_RESET_FIRE: box_runtime_reset_fire(&a->rt); break;
            case FFP_C_SIM_WX:
                box_wxsim_override(&r->wx, g[0], g[1], g[2] ? now + (int64_t)g[2] * 600 : 0);
                break;
            case FFP_C_SET_SF:
                if (g[0] >= 7 && g[0] <= 12) { r->sf = g[0]; if (a->hal->radio.set_sf) a->hal->radio.set_sf(a->hal->radio.ctx, g[0]); }
                break;
            default: break;
            }
        }
    }
}

static void build_status(const box_app_t *a, const box_output_t *o, const box_tick_t *t, bool force_alert, ffp_status_t *s)
{
    const box_retained_t *r = a->ret;
    unsigned fl = 0;
    int i;
    memset(s, 0, sizeof *s);
    s->state = o->sm.state;
    s->mode = a->rt.sm.survival ? FFP_MODE_SURVIVAL : (o->fwi.mode == FWI_MODE_ALERT || force_alert) ? FFP_MODE_ALERT : FFP_MODE_ECO;
    s->reasons = o->sm.reasons;
    s->gas_score = ffp_q8(o->gas.score, 255.0);
    s->gas_class = o->gas.cls;
    s->gas_faults = o->gas.faults;
    s->warmup = o->gas.warmup;
    s->scan_bad = o->gas.scan_bad;
    s->flame = o->flame_processed ? o->flame.detected : t->flame;
    s->cam_label = t->camera_valid ? t->camera_label : 0;
    s->cam_valid = t->camera_valid;
    s->cam_status = r->cam_status;
    s->cam_conf = t->camera_valid ? ffp_q8(t->camera_conf, 255.0) : 0;
    if (t->battery_low) fl |= FFP_SF_BATTERY_LOW;
    if (t->housing_hot) fl |= FFP_SF_HOUSING_HOT;
    if (t->supply_fault) fl |= FFP_SF_SUPPLY_FAULT;
    if (!r->clock_synced) fl |= FFP_SF_CLOCK_UNSYNCED;
    if (o->storage_errors > 0) fl |= FFP_SF_STORAGE_ERROR;
    if (o->sm.gps_on) fl |= FFP_SF_GPS_ON;
    if (o->sm.actuator) fl |= FFP_SF_PUMP;
    if (o->sm.camera_on) fl |= FFP_SF_CAMERA_ON;
    s->flags = (uint8_t)fl;
    s->fwi_x2 = ffp_q8(o->fwi.fwi, 2.0);
    s->danger = o->fwi.danger;
    s->fwi_updated = o->fwi_updated;
    s->provisional = o->fwi.provisional;
    s->battery_pct = (uint8_t)(a->hal->battery_pct ? a->hal->battery_pct(a->hal->ctx) : 100);
    if (s->battery_pct > 100) s->battery_pct = 100;
    for (i = 0; i < 3; i++) s->band[i] = ffp_q8(o->gas.bands[i], 64.0);
}

static void update_position(box_app_t *a, bool boot, int64_t now)
{
    const box_hal_t *h = a->hal;
    box_retained_t *r = a->ret;
    ffp_pos_t p;
    int64_t t_gps = -1;
    uint32_t timeout = boot ? a->cfg.gps_boot_timeout_ms : a->cfg.gps_alert_timeout_ms;
    if (!h->gps_poll) return;
    memset(&p, 0, sizeof p);
    if (h->gps_poll(h->ctx, &p, &t_gps, timeout)) {
        r->pos = p; r->pos.fix = 1; r->have_pos = true; r->last_gps_unix = now;
        if (t_gps > 1700000000 && !r->clock_synced) {          /* the GPS time is the first clock source */
            h->rtc_set_unix_s(h->ctx, t_gps);
            r->clock_synced = true;
        }
    }
}

double box_app_wake(box_app_t *a)
{
    const box_hal_t *h = a->hal;
    box_retained_t *r = a->ret;
    box_tick_t t;
    box_output_t o;
    box_downlinks_t dl;
    ffp_status_t st;
    double wind = 0.0, rain = 0.0, sleep_s;
    int64_t now;
    int i;
    uint32_t t0 = h->now_ms(h->ctx);
    bool force_alert, sent_any = false;

    memset(&dl, 0, sizeof dl);
    memset(&t, 0, sizeof t);
    r->wake_count++;

    /* ---- first wake-up after power-on: position and time from the GPS ---- */
    if (!r->booted) {
        h->gps_power(h->ctx, true);
        update_position(a, true, h->rtc_unix_s(h->ctx));
        h->gps_power(h->ctx, false);
        if (!r->have_pos && (a->cfg.static_lat_e7 || a->cfg.static_lon_e7)) {
            r->pos.lat_e7 = a->cfg.static_lat_e7; r->pos.lon_e7 = a->cfg.static_lon_e7; r->pos.fix = 0; r->have_pos = true;
        }
        r->booted = true;
    }

    now = h->rtc_unix_s(h->ctx);
    force_alert = r->force_alert_until_unix > now;

    /* ---- sensors ---- */
    t.unix_s = now;
    t.weather_valid = h->read_env(h->ctx, &t.temp_c, &t.rh_pct);
    box_wxsim_step(&r->wx, now, &wind, &rain);
    t.wind_kmh = wind;
    t.rain_mm = rain;
    t.battery_low = h->battery_low(h->ctx);
    t.housing_hot = h->housing_hot(h->ctx);
    t.supply_fault = h->supply_fault(h->ctx);
    h->flame_burst(h->ctx, t.flame_raw, a->cfg.rt.flame.burst_samples);
    t.flame_n = (uint8_t)a->cfg.rt.flame.burst_samples;
    if (!t.battery_low) {                                  /* Survival keeps the gas sensor off */
        h->gas_power(h->ctx, true);
        t.gas_valid = h->scan_gas(h->ctx, t.gas_ohm, t.gas_temp_c, t.gas_rh_pct);
        h->gas_power(h->ctx, false);
    }
    if (r->pending_camera) {                               /* capture finished at the previous wake-up */
        t.camera_valid = true; t.camera_label = r->pending_label; t.camera_conf = r->pending_conf;
        r->pending_camera = false;
    }

    /* ---- decision ---- */
    if (box_runtime_step(&a->rt, &t, &o) != 0) {
        a->last_tick = t;
        return 300.0;                                      /* bad arguments (RTC read failed?): try again later */
    }
    a->last_tick = t;
    a->last_out = o;
    h->gps_power(h->ctx, o.sm.gps_on);
    h->pump(h->ctx, o.sm.actuator);
    if (o.sm.gps_on && (now - r->last_gps_unix) >= 600) update_position(a, false, now);

    /* ---- frames ---- */
    build_status(a, &o, &t, force_alert, &st);
    a->last_priority_sent = 0;
    a->last_priority_acked = false;
    for (i = 0; i < o.sm.n_frames; i++) {
        uint8_t kind = o.sm.frames[i].kind;
        uint8_t type = kind <= 4 ? SM_TO_FFP[kind] : 0;
        if (!type) continue;
        if (type == FFP_T_HEARTBEAT) box_link_queue_status(&a->link, type, FFP_F_SIM_WX, &st);
        else {
            bool acked = false;
            a->last_priority_sent += box_link_send_priority(&a->link, type, FFP_F_SIM_WX, &st,
                                                            o.sm.frames[i].repeats ? o.sm.frames[i].repeats : 1, &acked, &dl, now);
            a->last_priority_acked = a->last_priority_acked || acked;
            sent_any = true;
        }
    }
    if (!r->clock_synced && (r->last_sync_req_unix == 0 || now - r->last_sync_req_unix >= 120)) {
        box_link_queue_status(&a->link, FFP_T_HEARTBEAT, FFP_F_SIM_WX, &st);      /* the ack comes with a TIME frame */
        r->last_sync_req_unix = now;
    }
    if (o.fwi_updated) {
        ffp_telem_t tm;
        memset(&tm, 0, sizeof tm);
        tm.temp_c100 = (int16_t)clampd(floor(t.temp_c * 100.0 + 0.5), -32768.0, 32767.0);
        tm.rh_x2 = ffp_q8(t.rh_pct, 2.0);
        tm.wind_kmh = ffp_q8(t.wind_kmh, 1.0);
        tm.rain_x10 = ffp_q8(t.rain_mm, 10.0);
        tm.ffmc_x2_5 = ffp_q8(o.fwi.ffmc, 2.5);
        tm.dmc = ffp_q8(o.fwi.dmc, 1.0);
        tm.dc = ffp_q16(o.fwi.dc, 1.0);
        tm.isi_x5 = ffp_q8(o.fwi.isi, 5.0);
        tm.bui = ffp_q8(o.fwi.bui, 1.0);
        tm.history_hours = o.fwi.history_hours > 24 ? 24 : o.fwi.history_hours;
        tm.provisional = o.fwi.provisional;
        box_link_queue_telem(&a->link, FFP_F_SIM_WX, &tm);
    }
    if (r->have_pos && (r->last_pos_queued_unix == 0 || (double)(now - r->last_pos_queued_unix) >= a->cfg.pos_period_s)) {
        box_link_queue_pos(&a->link, 0, &r->pos);
        r->last_pos_queued_unix = now;
    }
    a->last_flushed = 0;
    if (a->link.st->n > 0) {
        a->last_flushed = box_link_flush(&a->link, &dl, now);
        sent_any = true;
    }
    if (sent_any) box_link_listen(&a->link, a->cfg.rx_window_ms, &dl, now);   /* commands follow the ack */
    a->last_dl = dl.n;
    apply_downlink(a, &dl, now);

    force_alert = r->force_alert_until_unix > now;               /* a command received just now counts for the next sleep */

    /* ---- camera: after the radio, never at the same time ---- */
    a->last_camera_run = false;
    if (o.sm.camera_on && h->camera_hw) {
        const cam_hw_t *hw = h->camera_hw(h->ctx);
        if (hw) {
            cam_config_t cc;
            cam_ids_t ids;
            cam_result_t cr;
            cam_config_default(&cc);
            ids.box_id = a->cfg.box_id; ids.req_id = ++r->cam_req_id; ids.unix_s = now; ids.reasons = o.sm.reasons;
            memset(&cr, 0, sizeof cr);
            cam_session_run(hw, &cc, &ids, &a->cam_ws, a->cam_jpeg, sizeof a->cam_jpeg, &cr);
            r->cam_status = cr.status;
            if (cr.valid) { r->pending_label = cr.label; r->pending_conf = cr.conf; r->pending_camera = true; }
            a->last_camera_run = true;
        }
    }

    /* ---- next wake-up ---- */
    sleep_s = o.sm.interval_s;
    if (force_alert && o.sm.state == SM_NORMAL && !a->rt.sm.survival && sleep_s > a->cfg.rt.sm.alert_interval_s)
        sleep_s = a->cfg.rt.sm.alert_interval_s;                 /* gateway risk prior: scan like in Alert mode */
    sleep_s -= (double)(h->now_ms(h->ctx) - t0) / 1000.0;
    if (o.sm.state != SM_NORMAL && sleep_s > 2.0) {              /* Suspicion / Fire: stay reachable (relay, commands) */
        double lw = sleep_s < a->cfg.alert_listen_s ? sleep_s : a->cfg.alert_listen_s;
        memset(&dl, 0, sizeof dl);                              /* the first batch was applied above */
        box_link_listen(&a->link, (uint32_t)(lw * 1000.0), &dl, now);
        apply_downlink(a, &dl, now);
        sleep_s -= lw;
    }
    return sleep_s < 1.0 ? 1.0 : sleep_s;
}
