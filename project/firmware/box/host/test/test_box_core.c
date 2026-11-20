#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "box_app.h"
#include "mock_hal.h"
#include "nmea.h"

static int fails, checks;
#define CHECK(c) do { checks++; if (!(c)) { fails++; printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #c); } } while (0)

static mock_t mk;
static box_retained_t ret;
static box_app_t app;

static void setup(uint8_t id, uint8_t other)
{
    box_app_cfg_t c;
    mock_init(&mk);
    box_app_cfg_default(&c, id, other);
    c.gps_boot_timeout_ms = 1000;
    memset(&ret, 0, sizeof ret);
    CHECK(box_app_init(&app, &c, &mk.hal, &ret, NULL) == 0);
}

static void wake(int n)
{
    int i;
    for (i = 0; i < n; i++) {
        double s = box_app_wake(&app);
        mk.ms += (uint32_t)(s * 1000.0);
    }
}

/* a wake-up that has something to say (a heartbeat is due), so the radio window opens and the queued command arrives */
static double wake_hb(void) { double s; mk.ms += 700000; s = box_app_wake(&app); return s; }

static box_link_t mklink(box_link_state_t *st, uint8_t id, uint8_t other)
{
    box_link_t l;
    box_link_cfg_t c;
    box_link_cfg_default(&c);
    box_link_state_init(st);
    box_link_init(&l, &c, st, &mk.hal, id, other);
    return l;
}

/* ---------------- radio rules ---------------- */
static void test_link(void)
{
    box_link_state_t st;
    box_link_t l;
    ffp_status_t s;
    box_downlinks_t dl;
    bool acked;
    int sent;
    ffp_frame_t f;

    memset(&s, 0, sizeof s); s.state = 2;
    /* no gateway: the alert goes out 3 times, same sequence number, copies numbered */
    mock_init(&mk); mk.gw_dead = true;
    l = mklink(&st, 1, 2); memset(&dl, 0, sizeof dl);
    sent = box_link_send_priority(&l, FFP_T_ALERT, FFP_F_SIM_WX, &s, 3, &acked, &dl, 1000);
    CHECK(sent == 3 && !acked && mk.n_tx == 3);
    CHECK(mock_tx_decode(&mk, 0, &f) == 0 && f.type == FFP_T_ALERT && (f.flags & FFP_F_PRIORITY) && (f.flags & FFP_F_ACK_REQ) && (f.flags & FFP_F_SIM_WX));
    {
        ffp_frame_t g; ffp_status_t a, b;
        mock_tx_decode(&mk, 2, &g); ffp_unpack_status(&f, &a); ffp_unpack_status(&g, &b);
        CHECK(f.seq == g.seq && a.repeat == 0 && b.repeat == 2);
    }
    CHECK(mk.tx_ms[1] - mk.tx_ms[0] >= 1200);                               /* spaced copies */

    /* acknowledged after the first copy: stop */
    mock_init(&mk);
    l = mklink(&st, 1, 2); memset(&dl, 0, sizeof dl);
    sent = box_link_send_priority(&l, FFP_T_ALERT, 0, &s, 3, &acked, &dl, 1000);
    CHECK(sent == 1 && acked && dl.n == 1 && dl.items[0].kind == FFP_T_ACK);
    CHECK(box_link_gateway_reachable(&l, 1100));

    /* the gateway only answers from the 2nd copy */
    mock_init(&mk); mk.gw_ack_from_tx = 2;
    l = mklink(&st, 1, 2); memset(&dl, 0, sizeof dl);
    sent = box_link_send_priority(&l, FFP_T_ALERT, 0, &s, 3, &acked, &dl, 1000);
    CHECK(sent == 2 && acked);

    /* routine queue: kept without gateway, flushed in order when it answers */
    mock_init(&mk); mk.gw_dead = true;
    l = mklink(&st, 1, 2); memset(&dl, 0, sizeof dl);
    box_link_queue_status(&l, FFP_T_HEARTBEAT, 0, &s); box_link_queue_status(&l, FFP_T_HEARTBEAT, 0, &s);
    CHECK(st.n == 2 && box_link_flush(&l, &dl, 1000) == 0 && st.n == 2);
    CHECK(mk.n_tx == 2);                                                    /* one frame, routine_tries = 2 */
    mk.gw_dead = false; mk.n_tx = 0;
    CHECK(box_link_flush(&l, &dl, 2000) == 2 && st.n == 0);
    {
        ffp_frame_t a, b;
        mock_tx_decode(&mk, 0, &a); mock_tx_decode(&mk, 1, &b);
        CHECK(b.seq == (uint8_t)(a.seq + 1));
    }

    /* queue overflow drops the oldest heartbeat, not the alert-class frames */
    mock_init(&mk); mk.gw_dead = true;
    l = mklink(&st, 1, 2);
    { int i; for (i = 0; i < BOX_QN + 3; i++) box_link_queue_status(&l, i == 0 ? FFP_T_STATE : FFP_T_HEARTBEAT, 0, &s); }
    CHECK(st.n == BOX_QN && st.dropped_count == 3 && (st.q[0].bytes[0] >> 4) == FFP_T_STATE);

    /* relay: the neighbour's frame is heard and nobody acknowledges it */
    mock_init(&mk); mk.gw_dead = true;
    l = mklink(&st, 1, 2); memset(&dl, 0, sizeof dl);
    {
        ffp_frame_t n;
        ffp_frame_init(&n, FFP_T_ALERT, FFP_F_ACK_REQ, 2, FFP_ID_ANY_GW, 40); ffp_pack_status(&n, &s);
        mock_inject(&mk, &n, 100);
        box_link_listen(&l, 4000, &dl, 1000);
        CHECK(mk.n_tx == 1 && mock_tx_decode(&mk, 0, &f) == 0 && f.origin == 2 && f.seq == 40 && (f.flags & FFP_F_RELAYED) && st.relayed_count == 1);
        /* the same frame heard again is not relayed twice */
        mk.n_tx = 0; mock_inject(&mk, &n, mk.ms + 100); box_link_listen(&l, 4000, &dl, 1000);
        CHECK(mk.n_tx == 0);
        /* a relayed copy is never relayed again */
        ffp_frame_init(&n, FFP_T_ALERT, FFP_F_ACK_REQ | FFP_F_RELAYED, 2, FFP_ID_ANY_GW, 41); ffp_pack_status(&n, &s);
        mock_inject(&mk, &n, mk.ms + 100); box_link_listen(&l, 4000, &dl, 1000);
        CHECK(mk.n_tx == 0);
    }
    /* relay cancelled when a gateway acknowledges the neighbour's frame meanwhile */
    mock_init(&mk); mk.gw_dead = true;
    l = mklink(&st, 1, 2); memset(&dl, 0, sizeof dl);
    {
        ffp_frame_t n, a; ffp_ack_t k;
        ffp_frame_init(&n, FFP_T_ALERT, FFP_F_ACK_REQ, 2, FFP_ID_ANY_GW, 50); ffp_pack_status(&n, &s);
        k.acked_seq = 50; k.acked_type = FFP_T_ALERT; k.flags = 0; k.rssi_dbm = -90; k.snr_x4 = 0; k.gw_id = 8; k.alert_level = 0;
        ffp_frame_init(&a, FFP_T_ACK, 0, 8, 2, 0); ffp_pack_ack(&a, &k);
        mock_inject(&mk, &n, 100); mock_inject(&mk, &a, 400);
        box_link_listen(&l, 4000, &dl, 1000);
        CHECK(mk.n_tx == 0 && st.relayed_count == 0);
    }
    /* corrupted frames are counted and ignored */
    mock_init(&mk); mk.gw_dead = true;
    l = mklink(&st, 1, 2); memset(&dl, 0, sizeof dl);
    {
        ffp_frame_t n; uint8_t w[16];
        ffp_frame_init(&n, FFP_T_ALERT, 0, 2, 0, 5); ffp_encode(&n, w); w[6] ^= 0x40;
        mk.rxq[0].used = true; mk.rxq[0].at_ms = 10; memcpy(mk.rxq[0].w, w, 16);
        box_link_listen(&l, 500, &dl, 1000);
        CHECK(st.crc_errors == 1 && mk.n_tx == 0 && dl.n == 0);
    }
}

/* ---------------- one box through a day and a fire ---------------- */
static int count_type(int t) { return mock_count_tx(&mk, t); }

static void test_quiet_day(void)
{
    int i;
    setup(1, 2);
    mk.gps_has_fix = true; mk.gps_pos.lat_e7 = 365000000; mk.gps_pos.lon_e7 = 100000000; mk.gps_pos.alt_m = 120; mk.gps_pos.sats = 8;
    mk.gps_unix = mk.base_unix + 5;
    wake(1);
    CHECK(ret.clock_synced && ret.have_pos && ret.pos.fix == 1);
    wake(300);                                                              /* 300 wake-ups at 300 s = 25 h */
    CHECK(app.last_out.sm.state == SM_NORMAL);
    CHECK(count_type(FFP_T_ALERT) == 0);
    CHECK(count_type(FFP_T_HEARTBEAT) >= 140 && count_type(FFP_T_HEARTBEAT) <= 160);   /* every 600 s */
    CHECK(count_type(FFP_T_TELEM) >= 24 && count_type(FFP_T_TELEM) <= 27);            /* one per FWI hour */
    CHECK(count_type(FFP_T_POS) >= 1 && count_type(FFP_T_POS) <= 6);
    CHECK(ret.link.n == 0);
    for (i = 0; i < mk.n_tx; i++) { ffp_frame_t f; CHECK(mock_tx_decode(&mk, i, &f) == 0 && f.origin == 1); }
    /* a heartbeat carries the simulated-weather flag and the battery */
    {
        ffp_frame_t f; ffp_status_t s;
        for (i = mk.n_tx - 1; i >= 0; i--) { mock_tx_decode(&mk, i, &f); if (f.type == FFP_T_HEARTBEAT) break; }
        ffp_unpack_status(&f, &s);
        CHECK((f.flags & FFP_F_SIM_WX) && s.battery_pct == 80 && s.state == 0 && !(s.flags & FFP_SF_CLOCK_UNSYNCED));
    }
}

static void test_fire(void)
{
    int i, first_alert = -1;
    ffp_frame_t f; ffp_status_t s;
    setup(1, 2);
    wake(40);                                                               /* baseline learned on clean air */
    CHECK(app.last_out.sm.state == SM_NORMAL && count_type(FFP_T_ALERT) == 0);
    mk.gw_dead = true;                                                      /* the alert must not depend on the gateway */
    mk.gas_scale = 0.25; mk.flame_on = true;
    for (i = 0; i < 60; i++) {
        wake(1);
        if (first_alert < 0 && count_type(FFP_T_ALERT) > 0) first_alert = i;
        if (app.last_out.sm.state == SM_FIRE) break;
    }
    CHECK(app.last_out.sm.state == SM_FIRE && first_alert >= 0);
    CHECK(count_type(FFP_T_ALERT) >= 3);
    for (i = 0; i < mk.n_tx; i++) { mock_tx_decode(&mk, i, &f); if (f.type == FFP_T_ALERT) break; }
    ffp_unpack_status(&f, &s);
    CHECK(s.state == SM_FIRE && (s.reasons & SM_R_GAS) && (s.reasons & SM_R_FLAME) && s.gas_class == GC_SMOKE && s.flame == 1);
    CHECK(mk.pump_on == app.last_out.sm.actuator && mk.gps_on == app.last_out.sm.gps_on);
    CHECK(mk.cam_runs >= 1);

    /* the camera answer comes back at the next wake-up and travels in the frame */
    mk.cam_answer_label = "fire"; mk.cam_answer_conf = 0.9;
    wake(3);
    {
        int found = 0;
        for (i = 0; i < mk.n_tx; i++) { ffp_status_t q; mock_tx_decode(&mk, i, &f); if (f.type == FFP_T_ALERT) { ffp_unpack_status(&f, &q); if (q.cam_valid && q.cam_label == CAM_LABEL_FIRE) found = 1; } }
        CHECK(found);
    }
    /* the operator acknowledgement leaves Fire */
    mk.gw_dead = false; mk.gas_scale = 1.0; mk.flame_on = false; mk.gw_alert_level = 3;
    {
        ffp_frame_t a; ffp_ack_t k;
        k.acked_seq = f.seq; k.acked_type = FFP_T_ALERT; k.flags = FFP_AF_OPERATOR; k.rssi_dbm = -80; k.snr_x4 = 10; k.gw_id = 8; k.alert_level = 3;
        ffp_frame_init(&a, FFP_T_ACK, 0, 8, 1, 0); ffp_pack_ack(&a, &k);
        mock_inject(&mk, &a, mk.ms + 100);
        wake_hb();
        CHECK(ret.gw_alert_level == 3);
        CHECK(app.rt.sm.state == SM_NORMAL || app.rt.sm.state == SM_SUSPICION);
    }
}

static void test_last_gasp_and_survival(void)
{
    ffp_frame_t f; int i;
    setup(1, 2);
    wake(3);
    mk.supply_fault = true;
    wake(1);
    CHECK(count_type(FFP_T_LAST_GASP) >= 1);
    wake(2);
    { int n = count_type(FFP_T_LAST_GASP); wake(2); CHECK(count_type(FFP_T_LAST_GASP) == n); }   /* once */
    (void)f; (void)i;
    setup(1, 2);
    wake(3);
    mk.battery_low = true; mk.battery_pct = 8;
    { int g = mk.gas_calls; double s = box_app_wake(&app); CHECK(mk.gas_calls == g && s > 3000.0); }   /* Survival: no gas scan, 1 h sleep */
    {
        ffp_status_t st;
        mk.ms += 3600000; box_app_wake(&app); mk.ms += 700000; box_app_wake(&app);
        for (i = mk.n_tx - 1; i >= 0; i--) { mock_tx_decode(&mk, i, &f); if (f.type == FFP_T_HEARTBEAT) break; }
        ffp_unpack_status(&f, &st);
        CHECK(st.mode == FFP_MODE_SURVIVAL && (st.flags & FFP_SF_BATTERY_LOW));
    }
}

static void test_commands(void)
{
    ffp_frame_t c; ffp_cmd_t k; ffp_time_t tm;
    setup(1, 2);
    CHECK(!ret.clock_synced);
    wake(1);
    {   /* unsynced clock is reported */
        ffp_frame_t f; ffp_status_t s; int i;
        for (i = mk.n_tx - 1; i >= 0; i--) { mock_tx_decode(&mk, i, &f); if (f.type == FFP_T_HEARTBEAT) break; }
        if (f.type == FFP_T_HEARTBEAT) { ffp_unpack_status(&f, &s); CHECK(s.flags & FFP_SF_CLOCK_UNSYNCED); }
    }
    /* TIME */
    tm.unix_s = 1794000000u; tm.utc_offset_q = 4;
    ffp_frame_init(&c, FFP_T_TIME, 0, 8, 1, 1); ffp_pack_time(&c, &tm); mock_inject(&mk, &c, mk.ms + 5);
    wake(1);
    CHECK(ret.clock_synced && mk.hal.rtc_unix_s(&mk) >= 1794000000 && app.rt.cfg.utc_offset_s == 3600);
    /* nonsense time refused */
    tm.unix_s = 12345u; ffp_frame_init(&c, FFP_T_TIME, 0, 8, 1, 2); ffp_pack_time(&c, &tm); mock_inject(&mk, &c, mk.ms + 5);
    { int64_t before = mk.hal.rtc_unix_s(&mk); wake(1); CHECK(mk.hal.rtc_unix_s(&mk) >= before); }
    /* thresholds, bounded */
    k.id = FFP_C_SET_THRESH; memset(k.arg, 0, 6); k.arg[0] = 55; k.arg[1] = 30; k.arg[2] = 70;
    ffp_frame_init(&c, FFP_T_CMD, 0, 8, 1, 3); ffp_pack_cmd(&c, &k); mock_inject(&mk, &c, mk.ms + 5);
    wake_hb();
    CHECK(fabs(app.rt.gas.cfg.smoke_on - 0.55) < 1e-9 && fabs(app.rt.gas.cfg.smoke_off - 0.30) < 1e-9 && fabs(app.rt.sm.cfg.camera_confidence - 0.70) < 1e-9);
    k.arg[0] = 2; k.arg[1] = 99; k.arg[2] = 5;                               /* absurd: clamped, detection cannot be switched off */
    ffp_frame_init(&c, FFP_T_CMD, 0, 8, 1, 4); ffp_pack_cmd(&c, &k); mock_inject(&mk, &c, mk.ms + 5);
    wake_hb();
    CHECK(app.rt.gas.cfg.smoke_on <= 0.80 + 1e-9 && app.rt.gas.cfg.smoke_on >= 0.25 - 1e-9 && app.rt.gas.cfg.smoke_off <= app.rt.gas.cfg.smoke_on && app.rt.sm.cfg.camera_confidence >= 0.40 - 1e-9);
    /* force alert: scan every 30 s though the FWI says Eco; wind override is flagged */
    k.id = FFP_C_FORCE_MODE; memset(k.arg, 0, 6); k.arg[0] = 2; k.arg[1] = 1;
    ffp_frame_init(&c, FFP_T_CMD, 0, 8, 1, 5); ffp_pack_cmd(&c, &k); mock_inject(&mk, &c, mk.ms + 5);
    wake_hb();
    { double s = box_app_wake(&app); CHECK(s > 20.0 && s <= 30.0); }
    k.id = FFP_C_FORCE_MODE; k.arg[0] = 1;                                   /* "force eco" cannot lower anything */
    ffp_frame_init(&c, FFP_T_CMD, 0, 8, 1, 6); ffp_pack_cmd(&c, &k); mock_inject(&mk, &c, mk.ms + 5);
    { double s = box_app_wake(&app); mk.ms += (uint32_t)(s * 1000); s = box_app_wake(&app); CHECK(s <= 30.0); }
    k.id = FFP_C_SIM_WX; memset(k.arg, 0, 6); k.arg[0] = 45; k.arg[1] = 0; k.arg[2] = 1;
    ffp_frame_init(&c, FFP_T_CMD, 0, 8, 1, 7); ffp_pack_cmd(&c, &k); mock_inject(&mk, &c, mk.ms + 5);
    wake_hb();
    mk.ms += 30000; box_app_wake(&app);
    CHECK(app.last_tick.wind_kmh == 45.0);
    k.id = FFP_C_SET_SF; memset(k.arg, 0, 6); k.arg[0] = 11;
    ffp_frame_init(&c, FFP_T_CMD, 0, 8, 1, 8); ffp_pack_cmd(&c, &k); mock_inject(&mk, &c, mk.ms + 5);
    wake_hb();
    CHECK(mk.sf == 11 && ret.sf == 11);
    /* a command repeated by the gateway (same sequence number) is applied once */
    k.id = FFP_C_SIM_WX; k.arg[0] = 10;
    ffp_frame_init(&c, FFP_T_CMD, 0, 8, 1, 9); ffp_pack_cmd(&c, &k);
    mock_inject(&mk, &c, mk.ms + 5); mock_inject(&mk, &c, mk.ms + 900);
    wake_hb();
    CHECK(app.last_dl >= 1);
}

static void test_survives_bad_inputs(void)
{
    setup(1, 2);
    mk.env_ok = false; mk.gas_ok = false;
    wake(5);                                                                 /* sensors failing: no crash, heartbeats still go */
    CHECK(app.last_out.sm.state == SM_NORMAL);
    mk.base_unix = -100000;                                                  /* clock unreadable */
    { double s = box_app_wake(&app); CHECK(s == 300.0); }
}

static void test_nmea(void)
{
    nmea_fix_t f;
    memset(&f, 0, sizeof f);
    CHECK(nmea_feed(&f, "$GPGGA,123519,3653.100,N,01006.900,E,1,08,0.9,545.4,M,46.9,M,,*47") == -1);   /* wrong checksum */
    {   /* compute valid checksums on the fly */
        char s[128]; const char *body; unsigned cs; const char *p;
        body = "GPGGA,123519,3653.100,N,01006.900,E,1,08,0.9,545.4,M,46.9,M,,";
        for (cs = 0, p = body; *p; p++) cs ^= (unsigned char)*p;
        snprintf(s, sizeof s, "$%s*%02X\r\n", body, cs);
        CHECK(nmea_feed(&f, s) == 1 && f.have_pos && f.sats == 8 && f.alt_m == 545);
        CHECK(llabs((long long)f.lat_e7 - 368850000LL) < 5 && llabs((long long)f.lon_e7 - 101150000LL) < 5);
        body = "GPRMC,123519,A,3653.100,N,01006.900,E,0.0,0.0,051126,,,A";
        for (cs = 0, p = body; *p; p++) cs ^= (unsigned char)*p;
        snprintf(s, sizeof s, "$%s*%02X", body, cs);
        CHECK(nmea_feed(&f, s) == 1 && f.have_time);
        CHECK(f.unix_s == 1793882119LL);                                      /* 2026-11-05 12:35:19 UTC */
        body = "GPGGA,123519,,,,,0,00,,,M,,M,,";
        for (cs = 0, p = body; *p; p++) cs ^= (unsigned char)*p;
        snprintf(s, sizeof s, "$%s*%02X", body, cs);
        memset(&f, 0, sizeof f);
        CHECK(nmea_feed(&f, s) == 0 && !f.have_pos);                          /* no fix: nothing taken */
        body = "GPGSV,3,1,11,03,03,111,00";
        for (cs = 0, p = body; *p; p++) cs ^= (unsigned char)*p;
        snprintf(s, sizeof s, "$%s*%02X", body, cs);
        CHECK(nmea_feed(&f, s) == 0);
    }
    CHECK(nmea_feed(&f, "garbage") == -1);
}

static void test_wxsim(void)
{
    box_wxsim_t a, b;
    double wa, ra, wb, rb, rain_total = 0, wmax = 0, wmin = 99;
    int i;
    box_wxsim_init(&a, 7); box_wxsim_init(&b, 7);
    for (i = 0; i < 24 * 30; i++) {
        box_wxsim_step(&a, 1793800000 + i * 3600, &wa, &ra);
        box_wxsim_step(&b, 1793800000 + i * 3600, &wb, &rb);
        CHECK(wa == wb && ra == rb);
        rain_total += ra; if (wa > wmax) wmax = wa; if (wa < wmin) wmin = wa;
    }
    CHECK(wmax <= 60.0 && wmin >= 0.0 && rain_total > 0.0 && rain_total < 200.0);
    box_wxsim_override(&a, 50, 30, 1793800000 + 24 * 30 * 3600 + 7200);
    box_wxsim_step(&a, 1793800000 + 24 * 30 * 3600 + 3600, &wa, &ra);
    CHECK(wa == 50.0 && fabs(ra - 6.0) < 1e-9);
    box_wxsim_step(&a, 1793800000 + 24 * 30 * 3600 + 8000, &wa, &ra);
    CHECK(wa < 50.0);                                                         /* override expired */
}

int main(void)
{
    test_link();
    test_quiet_day();
    test_fire();
    test_last_gasp_and_survival();
    test_commands();
    test_survives_bad_inputs();
    test_nmea();
    test_wxsim();
    printf("%d checks, %d failed\n", checks, fails);
    return fails ? 1 : 0;
}
