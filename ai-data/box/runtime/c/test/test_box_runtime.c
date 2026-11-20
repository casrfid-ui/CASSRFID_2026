/* Tests of the runtime glue: hourly FWI, local time, gas chain, state machine, flash copies, reboots. */
#include <math.h>
#include <stdio.h>
#include <string.h>
#include "box_runtime.h"

static int failures = 0, checks = 0;
#define CHECK(cond) do { checks++; if (!(cond)) { failures++; printf("FAIL line %d: %s\n", __LINE__, #cond); } } while (0)

#define T0 1784073600LL                       /* 2026-07-15 00:00:00 UTC */

/* RAM key-value store standing for the NVS */
typedef struct { char key[16]; uint8_t data[256]; int len; } slot_t;
typedef struct { slot_t slot[8]; int n; int fail_write; int writes; } ram_t;
static slot_t *find(ram_t *r, const char *k) { int i; for (i = 0; i < r->n; i++) if (!strcmp(r->slot[i].key, k)) return &r->slot[i]; return NULL; }
static int ram_read(void *c, const char *k, uint8_t *b, size_t n) { slot_t *s = find(c, k); if (!s) return -1; if ((size_t)s->len < n) n = (size_t)s->len; memcpy(b, s->data, n); return (int)n; }
static int ram_write(void *c, const char *k, const uint8_t *b, size_t n)
{
    ram_t *r = c; slot_t *s;
    if (r->fail_write) return -1;
    s = find(r, k);
    if (!s) { s = &r->slot[r->n++]; strcpy(s->key, k); }
    memcpy(s->data, b, n); s->len = (int)n; r->writes++;
    return 0;
}
static box_kv_t kv_of(ram_t *r) { box_kv_t kv; kv.read = ram_read; kv.write = ram_write; kv.ctx = r; return kv; }

/* ---- synthetic input ---- */
static unsigned rs = 99u;
static double noise(void) { rs = rs * 1664525u + 1013904223u; return ((double)(rs >> 8) / 16777216.0 - 0.5) * 0.034; }
static box_tick_t tick(int64_t unix_s)
{
    box_tick_t t; memset(&t, 0, sizeof t);
    t.unix_s = unix_s; t.weather_valid = true; t.temp_c = 30.0; t.rh_pct = 30.0; t.wind_kmh = 15.0;
    return t;
}
static void add_gas(box_tick_t *t, double drop)
{
    int i;
    t->gas_valid = true;
    for (i = 0; i < GC_NSTEP; i++) { t->gas_ohm[i] = exp(11.5 + 2.0 * i / 9.0 - drop + noise()); t->gas_temp_c[i] = 25.0; t->gas_rh_pct[i] = 50.0; }
}
static box_output_t go(box_runtime_t *rt, const box_tick_t *t) { box_output_t o; CHECK(box_runtime_step(rt, t, &o) == 0); return o; }

/* run n gas scans at 30 s from time *u, return last output */
static box_output_t scans(box_runtime_t *rt, int64_t *u, int n, double drop)
{
    box_output_t o; int i; memset(&o, 0, sizeof o);
    for (i = 0; i < n; i++) { box_tick_t t = tick(*u); add_gas(&t, drop); o = go(rt, &t); *u += 30; }
    return o;
}

static void test_init_without_flash(void)
{
    box_runtime_t rt;
    CHECK(box_runtime_init(&rt, NULL, NULL) == 0);
    CHECK(rt.sm.state == SM_NORMAL && rt.fwi.state.ffmc == 85.0);
    CHECK(box_runtime_init(NULL, NULL, NULL) == -1);
}

static void test_bad_arguments(void)
{
    box_runtime_t rt; box_tick_t t = tick(T0); box_output_t o; box_config_t c;
    box_runtime_init(&rt, NULL, NULL);
    CHECK(box_runtime_step(NULL, &t, &o) == -1 && box_runtime_step(&rt, NULL, &o) == -1 && box_runtime_step(&rt, &t, NULL) == -1);
    t.unix_s = -5; CHECK(box_runtime_step(&rt, &t, &o) == -1);
    box_config_default(&c); c.gas.median_window = 99; CHECK(box_runtime_init(&rt, &c, NULL) == -1);
    box_config_default(&c); c.baseline_save_period_s = 0.0; CHECK(box_runtime_init(&rt, &c, NULL) == -1);
}

static void test_fwi_once_per_hour(void)
{
    box_runtime_t rt; box_output_t o; int64_t u; int updates = 0;
    box_runtime_init(&rt, NULL, NULL);
    for (u = T0 + 600; u < T0 + 600 + 3 * 3600; u += 300) { box_tick_t t = tick(u); o = go(&rt, &t); updates += o.fwi_updated; }
    CHECK(updates == 4);                                   /* 00:10 first tick, then 01:00, 02:00, 03:00 */
    CHECK(rt.fwi.state.real_hours == 4 && o.fwi.provisional == 1);
}

static void test_rain_is_accumulated_between_fwi_hours(void)
{
    box_runtime_t rt; box_output_t o; int64_t u;
    box_runtime_init(&rt, NULL, NULL);
    { box_tick_t t = tick(T0 + 60); go(&rt, &t); }        /* first update, history: 0 */
    for (u = T0 + 360; u < T0 + 3600; u += 300) { box_tick_t t = tick(u); t.rain_mm = 0.5; go(&rt, &t); }
    { box_tick_t t = tick(T0 + 3600); t.rain_mm = 0.5; o = go(&rt, &t); }
    CHECK(o.fwi_updated);
    {
        int n = 0; for (u = T0 + 360; u < T0 + 3600; u += 300) n++;
        CHECK(fabs(fwi_rain_24h(&rt.fwi.state) - 0.5 * (n + 1)) < 1e-12);
    }
}

static void test_local_time_and_month(void)
{
    /* box at UTC+2, 2026-07-15 09:59 UTC = 11:59 local, then 10:00 UTC = 12:00 local: DMC and DC must move at 12:00 local */
    box_runtime_t rt; box_config_t c; box_output_t o; fwi_engine_t ref; fwi_input_t in; fwi_output_t ro;
    box_config_default(&c); c.utc_offset_s = 7200;
    box_runtime_init(&rt, &c, NULL);
    { box_tick_t t = tick(T0 + 9 * 3600 + 59 * 60); o = go(&rt, &t); CHECK(o.fwi_updated); }
    { box_tick_t t = tick(T0 + 10 * 3600); o = go(&rt, &t); CHECK(o.fwi_updated); }
    fwi_engine_init(&ref, NULL, NULL, NULL);
    in.hour = 11; in.month = 7; in.temp_c = 30.0; in.rh_pct = 30.0; in.wind_kmh = 15.0; in.rain_mm = 0.0;
    fwi_engine_update_hour(&ref, &in, &ro);
    in.hour = 12; fwi_engine_update_hour(&ref, &in, &ro);
    CHECK(o.fwi.dmc == ro.dmc && o.fwi.dc == ro.dc && o.fwi.ffmc == ro.ffmc && o.fwi.fwi == ro.fwi);
    CHECK(o.fwi.dmc > 6.0);
    /* month change at midnight local: 2026-07-31 22:30 UTC with +2 h is already 1 August */
    box_runtime_init(&rt, &c, NULL);
    { box_tick_t t = tick(T0 + 16 * 86400 + 22 * 3600 + 1800); o = go(&rt, &t); CHECK(o.fwi_updated); }
}

static void test_invalid_weather_defers_the_hour(void)
{
    box_runtime_t rt; box_output_t o;
    box_runtime_init(&rt, NULL, NULL);
    { box_tick_t t = tick(T0 + 10); t.temp_c = NAN; t.rain_mm = 1.5; o = go(&rt, &t); }
    CHECK(!o.fwi_updated && o.fwi_status == FWI_ERR_INPUT && rt.fwi.state.real_hours == 0);
    CHECK(o.sm.state == SM_NORMAL);                                   /* the box keeps running on the last known values */
    { box_tick_t t = tick(T0 + 40); t.weather_valid = false; o = go(&rt, &t); CHECK(!o.fwi_updated); }
    { box_tick_t t = tick(T0 + 70); t.rain_mm = 0.5; o = go(&rt, &t); }
    CHECK(o.fwi_updated && fabs(fwi_rain_24h(&rt.fwi.state) - 2.0) < 1e-12);   /* no rain lost */
}

static void test_alert_mode_changes_interval(void)
{
    box_runtime_t rt; box_output_t o; int h;
    box_runtime_init(&rt, NULL, NULL);
    { box_tick_t t = tick(T0 + 10); t.temp_c = 38.0; t.rh_pct = 12.0; t.wind_kmh = 40.0; o = go(&rt, &t); }
    CHECK(o.fwi_updated && o.fwi.mode == FWI_MODE_ECO && o.sm.interval_s == 300.0);          /* one hot hour is not enough */
    for (h = 1; h < 8; h++) { box_tick_t t = tick(T0 + 10 + 3600 * h); t.temp_c = 38.0; t.rh_pct = 12.0; t.wind_kmh = 40.0; o = go(&rt, &t); }
    CHECK(o.fwi.mode == FWI_MODE_ALERT && o.fwi.danger >= 3 && o.sm.interval_s == 30.0);
    { box_tick_t t = tick(T0 + 40 + 3600 * 7); o = go(&rt, &t); }                              /* same hour: mode kept */
    CHECK(!o.fwi_updated && o.sm.interval_s == 30.0);
}

static void test_gas_to_fire_and_frames(void)
{
    box_runtime_t rt; box_output_t o; int64_t u = T0 + 100; int i, got_susp = 0;
    box_runtime_init(&rt, NULL, NULL);
    scans(&rt, &u, 30, 0.0);
    for (i = 0; i < 12; i++) { o = scans(&rt, &u, 1, 0.4); if (o.sm.state == SM_SUSPICION) got_susp = 1; }
    CHECK(got_susp && o.sm.camera_on + o.sm.gps_on >= 1);
    { box_tick_t t = tick(u); add_gas(&t, 0.4); t.camera_valid = true; t.camera_label = SM_CAM_FIRE; t.camera_conf = 0.9; o = go(&rt, &t); }
    CHECK(o.sm.state == SM_FIRE && o.sm.actuator && o.sm.n_frames >= 1 && o.sm.frames[0].kind == SM_FRAME_ALERT);
}

static void test_survival_stops_gas(void)
{
    box_runtime_t rt; box_output_t o; int64_t u = T0 + 100;
    box_runtime_init(&rt, NULL, NULL);
    scans(&rt, &u, 30, 0.0);
    { box_tick_t t = tick(u); add_gas(&t, 0.6); t.battery_low = true; o = go(&rt, &t); }
    CHECK(!o.want_gas_scan && !o.gas_scanned && o.sm.interval_s == 3600.0 && o.sm.state == SM_NORMAL);
}

static void test_flash_copies_and_reboot(void)
{
    ram_t ram; box_kv_t kv; box_runtime_t rt, rt2; box_output_t o; int64_t u = T0 + 100; int i, mask;
    memset(&ram, 0, sizeof ram); kv = kv_of(&ram);
    CHECK(box_runtime_init(&rt, NULL, &kv) == 0);
    o = scans(&rt, &u, 40, 0.0);
    CHECK(find(&ram, BOX_KEY_GAS) != NULL && find(&ram, BOX_KEY_FWI) != NULL && find(&ram, BOX_KEY_META) != NULL);
    CHECK(o.storage_errors == 0);
    /* reboot: baseline, FWI state and meta are back, the first scan is already scored (no warm-up) */
    mask = box_runtime_init(&rt2, NULL, &kv);
    CHECK((mask & BOX_RESTORED_GAS) && (mask & BOX_RESTORED_FWI) && (mask & BOX_RESTORED_META));
    { box_tick_t t = tick(u); add_gas(&t, 0.0); o = go(&rt2, &t); }
    CHECK(!o.gas.warmup);
    CHECK(!o.fwi_updated && o.fwi.ffmc == rt.fwi_last.ffmc);          /* same hour: not applied twice */
    CHECK(rt2.fwi.state.real_hours == rt.fwi.state.real_hours);
    /* a different hour is applied normally */
    { box_tick_t t = tick(u + 3600); o = go(&rt2, &t); CHECK(o.fwi_updated); }
    /* corrupted baseline is refused */
    for (i = 0; i < ram.n; i++) if (!strcmp(ram.slot[i].key, BOX_KEY_GAS)) ram.slot[i].data[12] ^= 0x40;
    mask = box_runtime_init(&rt2, NULL, &kv);
    CHECK(!(mask & BOX_RESTORED_GAS));
}

static void test_fire_survives_a_reboot_until_reset(void)
{
    ram_t ram; box_kv_t kv; box_runtime_t rt, rt2, rt3; box_output_t o; int64_t u = T0 + 100; int mask;
    memset(&ram, 0, sizeof ram); kv = kv_of(&ram);
    box_runtime_init(&rt, NULL, &kv);
    scans(&rt, &u, 30, 0.0);
    scans(&rt, &u, 4, 0.4);
    { box_tick_t t = tick(u); add_gas(&t, 0.4); t.camera_valid = true; t.camera_label = SM_CAM_SMOKE; t.camera_conf = 0.8; o = go(&rt, &t); }
    CHECK(o.sm.state == SM_FIRE);
    mask = box_runtime_init(&rt2, NULL, &kv);
    CHECK((mask & BOX_RESTORED_SM) && rt2.sm.state == SM_FIRE);
    { box_tick_t t = tick(u + 60); o = go(&rt2, &t); }
    CHECK(o.sm.state == SM_FIRE && o.sm.actuator);
    box_runtime_reset_fire(&rt2);
    box_runtime_init(&rt3, NULL, &kv);
    CHECK(rt3.sm.state == SM_NORMAL);
}

static void test_last_gasp_not_repeated_after_reboot(void)
{
    ram_t ram; box_kv_t kv; box_runtime_t rt, rt2; box_output_t o;
    memset(&ram, 0, sizeof ram); kv = kv_of(&ram);
    box_runtime_init(&rt, NULL, &kv);
    { box_tick_t t = tick(T0 + 10); t.housing_hot = true; o = go(&rt, &t); CHECK(o.sm.last_gasp); }
    box_runtime_init(&rt2, NULL, &kv);
    { box_tick_t t = tick(T0 + 40); t.housing_hot = true; o = go(&rt2, &t); CHECK(!o.sm.last_gasp); }
}

static void test_storage_failures_are_reported_not_fatal(void)
{
    ram_t ram; box_kv_t kv; box_runtime_t rt; box_output_t o; int64_t u = T0 + 100; int errs = 0, i;
    memset(&ram, 0, sizeof ram); ram.fail_write = 1; kv = kv_of(&ram);
    box_runtime_init(&rt, NULL, &kv);
    for (i = 0; i < 40; i++) { o = scans(&rt, &u, 1, 0.0); errs += o.storage_errors; }
    CHECK(errs > 0 && o.sm.state == SM_NORMAL && !o.gas.warmup);
}

static void test_clock_going_backwards(void)
{
    box_runtime_t rt; box_output_t o;
    box_runtime_init(&rt, NULL, NULL);
    { box_tick_t t = tick(T0 + 1000); go(&rt, &t); }
    { box_tick_t t = tick(T0 + 500); o = go(&rt, &t); }
    CHECK(o.clock_jump);
    { box_tick_t t = tick(T0 + 530); o = go(&rt, &t); CHECK(!o.clock_jump); }
}

static void test_baseline_not_saved_while_smoke(void)
{
    ram_t ram; box_kv_t kv; box_runtime_t rt; int64_t u = T0 + 100; int w0;
    memset(&ram, 0, sizeof ram); kv = kv_of(&ram);
    box_runtime_init(&rt, NULL, &kv);
    scans(&rt, &u, 40, 0.0);
    scans(&rt, &u, 8, 0.4);
    w0 = ram.writes;
    scans(&rt, &u, 20, 0.4);
    { slot_t *s = find(&ram, BOX_KEY_GAS); CHECK(s != NULL); }
    CHECK(ram.writes - w0 <= 2);                                      /* only FWI/meta hour writes, no baseline write */
}

static void test_flame_burst_replaces_the_flag(void)
{
    box_runtime_t rt; box_output_t o; int i;
    box_runtime_init(&rt, NULL, NULL);
    for (i = 0; i < 8; i++) { box_tick_t t = tick(T0 + 10 + 30 * i); o = go(&rt, &t); }
    /* two bursts with a lone glitch: no flame, the machine stays Normal */
    for (i = 0; i < 3; i++) {
        box_tick_t t = tick(T0 + 300 + 30 * i); memset(t.flame_raw, 1, 8); t.flame_raw[3] = 0; t.flame_n = 8;
        o = go(&rt, &t);
        CHECK(o.flame_processed && !o.flame.detected && o.sm.state == SM_NORMAL);
    }
    /* the plain flag is ignored when a burst is present */
    { box_tick_t t = tick(T0 + 400); t.flame = true; memset(t.flame_raw, 1, 8); t.flame_n = 8; o = go(&rt, &t); CHECK(o.sm.state == SM_NORMAL); }
    /* two lit bursts in a row (active low: reads at 0) start a suspicion */
    for (i = 0; i < 2; i++) {
        box_tick_t t = tick(T0 + 500 + 30 * i); memset(t.flame_raw, 0, 8); t.flame_n = 8; o = go(&rt, &t);
        CHECK(o.flame.detected && o.flame.ratio == 1.0);
    }
    CHECK(o.sm.state == SM_SUSPICION && (o.sm.reasons & SM_R_FLAME));
    /* a refused burst falls back to the plain flag */
    { box_tick_t t = tick(T0 + 600); t.flame_n = FL_MAX_SAMPLES; t.flame = false; o = go(&rt, &t); CHECK(o.flame_processed); }
    box_runtime_init(&rt, NULL, NULL);
    { box_tick_t t = tick(T0 + 10); t.flame_n = 200; o = go(&rt, &t); CHECK(!o.flame_processed && o.flame_status == -1); }
}

int main(void)
{
    test_init_without_flash(); test_bad_arguments(); test_fwi_once_per_hour(); test_rain_is_accumulated_between_fwi_hours();
    test_local_time_and_month(); test_invalid_weather_defers_the_hour(); test_alert_mode_changes_interval();
    test_gas_to_fire_and_frames(); test_survival_stops_gas(); test_flash_copies_and_reboot();
    test_fire_survives_a_reboot_until_reset(); test_last_gasp_not_repeated_after_reboot();
    test_storage_failures_are_reported_not_fatal(); test_clock_going_backwards(); test_baseline_not_saved_while_smoke();
    test_flame_burst_replaces_the_flag();
    printf("%d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
