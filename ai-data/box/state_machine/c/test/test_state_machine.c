/* Unit tests of the C state machine: the 18 cases of python/tests/test_machine.py, plus bad arguments. */
#include <stdio.h>
#include <string.h>
#include "state_machine.h"

static int failures = 0, checks = 0;
#define CHECK(cond) do { checks++; if (!(cond)) { failures++; printf("FAIL line %d: %s\n", __LINE__, #cond); } } while (0)

/* build inputs like Python's Inputs(**kw) */
static sm_inputs_t in(void) { sm_inputs_t x; sm_inputs_default(&x); return x; }
static sm_output_t go(sm_machine_t *m, sm_inputs_t x)
{
    sm_output_t o;
    CHECK(sm_step(m, &x, &o) == 0);
    return o;
}
static sm_inputs_t gas(void) { sm_inputs_t x = in(); x.gas_smoke = true; return x; }
static void cam(sm_inputs_t *x, int label, double conf) { x->camera_valid = true; x->camera_label = (uint8_t)label; x->camera_conf = conf; }
static bool has_frame(const sm_output_t *o, int kind, int rep)
{
    int i;
    for (i = 0; i < o->n_frames; i++) if (o->frames[i].kind == kind && o->frames[i].repeats == rep) return true;
    return false;
}
static void to_suspicion(sm_machine_t *m) { sm_init(m, NULL); CHECK(go(m, gas()).state == SM_SUSPICION); }
static void to_fire(sm_machine_t *m)
{
    sm_inputs_t x = gas();
    to_suspicion(m);
    cam(&x, SM_CAM_FIRE, 0.95);
    CHECK(go(m, x).state == SM_FIRE);
}

static void test_start_normal(void)
{
    sm_machine_t m; sm_output_t o;
    sm_init(&m, NULL);
    o = go(&m, in());
    CHECK(o.state == SM_NORMAL && !o.camera_on && !o.gps_on && !o.actuator && o.n_frames == 0);
}

static void test_intervals(void)
{
    sm_machine_t m; sm_inputs_t x = in();
    sm_init(&m, NULL);
    CHECK(go(&m, x).interval_s == 300.0);
    x.fwi_mode = SM_FWI_ALERT; CHECK(go(&m, x).interval_s == 30.0);
    x = in(); x.battery_low = true; CHECK(go(&m, x).interval_s == 3600.0);
}

static void test_gas_starts_suspicion(void)
{
    sm_machine_t m; sm_output_t o;
    sm_init(&m, NULL);
    o = go(&m, gas());
    CHECK(o.state == SM_SUSPICION && o.camera_on && o.gps_on && o.interval_s == 30.0 && (o.reasons & SM_R_GAS));
}

static void test_flame_needs_two_reads(void)
{
    sm_machine_t m; sm_inputs_t f = in(), n = in(); sm_output_t o;
    f.flame = true;
    sm_init(&m, NULL);
    CHECK(go(&m, f).state == SM_NORMAL);
    CHECK(go(&m, n).state == SM_NORMAL);
    CHECK(go(&m, f).state == SM_NORMAL);
    o = go(&m, f);
    CHECK(o.state == SM_SUSPICION && (o.reasons & SM_R_FLAME));
}

static void test_camera_confirms(void)
{
    sm_machine_t m; sm_inputs_t x = gas(); sm_output_t o;
    to_suspicion(&m);
    cam(&x, SM_CAM_SMOKE, 0.9);
    o = go(&m, x);
    CHECK(o.state == SM_FIRE && has_frame(&o, SM_FRAME_ALERT, 3) && o.actuator && (o.reasons & SM_R_CAMERA));
}

static void test_weak_or_background_camera(void)
{
    sm_machine_t m; sm_inputs_t x = gas();
    to_suspicion(&m);
    cam(&x, SM_CAM_FIRE, 0.4); CHECK(go(&m, x).state == SM_SUSPICION);
    cam(&x, SM_CAM_BACKGROUND, 0.99); CHECK(go(&m, x).state == SM_SUSPICION);
    cam(&x, 77, 0.99); CHECK(go(&m, x).state == SM_SUSPICION);          /* unknown label never confirms */
}

static void test_gas_and_flame(void)
{
    sm_machine_t m; sm_inputs_t x = gas();
    sm_init(&m, NULL);
    go(&m, x);
    x.flame = true;
    go(&m, x);
    CHECK(go(&m, x).state == SM_FIRE);
}

static void test_second_witness(void)
{
    sm_machine_t m; sm_inputs_t x; int i, k, fire = 0;
    for (k = 0; k < 2; k++) {
        x = in();
        if (k == 0) x.gas_smoke = true; else x.flame = true;
        sm_init(&m, NULL);
        for (i = 0; i < 200; i++) if (go(&m, x).state == SM_FIRE) fire = 1;
    }
    CHECK(!fire);
}

static void test_clears(void)
{
    sm_machine_t m; sm_output_t o; int i, seen_susp = 0;
    to_suspicion(&m);
    for (i = 0; i < 10; i++) { o = go(&m, in()); if (i < 9 && o.state == SM_SUSPICION) seen_susp++; }
    CHECK(o.state == SM_NORMAL && seen_susp == 9);
}

static void test_trigger_resets_clear_counter(void)
{
    sm_machine_t m; int i;
    to_suspicion(&m);
    for (i = 0; i < 9; i++) go(&m, in());
    go(&m, gas());
    CHECK(go(&m, in()).state == SM_SUSPICION);
}

static void test_fire_latched(void)
{
    sm_machine_t m, m2; sm_inputs_t x = in();
    x.dt_s = 600.0;
    to_fire(&m);
    CHECK(go(&m, x).state == SM_FIRE);
    CHECK(go(&m, x).state == SM_FIRE);
    CHECK(go(&m, x).state == SM_NORMAL);
    to_fire(&m2);
    sm_reset(&m2);
    CHECK(go(&m2, in()).state == SM_NORMAL);
}

static void test_trigger_inside_fire_restarts_hold(void)
{
    sm_machine_t m; sm_inputs_t x = in(), g = gas();
    to_fire(&m);
    x.dt_s = 1500.0; go(&m, x);
    g.dt_s = 30.0; go(&m, g);
    CHECK(go(&m, x).state == SM_FIRE);
}

static void test_camera_period(void)
{
    sm_machine_t m; sm_inputs_t x = gas(); int i, woke = 0;
    sm_init(&m, NULL);
    x.dt_s = 10.0;
    for (i = 0; i < 9; i++) woke += go(&m, x).camera_on;
    CHECK(woke == 3);
}

static void test_pump(void)
{
    sm_machine_t m, m2; sm_inputs_t x = in(); sm_output_t o;
    sm_init(&m, NULL);
    x.fwi_danger = 4; CHECK(!go(&m, x).actuator);
    x = gas(); x.fwi_danger = 4; o = go(&m, x);
    CHECK(o.actuator && (o.reasons & SM_R_FWI));
    sm_init(&m2, NULL);
    x = gas(); x.fwi_danger = 1; CHECK(!go(&m2, x).actuator);
}

static void test_last_gasp(void)
{
    sm_machine_t m; sm_inputs_t x = in(); sm_output_t a, b;
    sm_init(&m, NULL);
    x.housing_hot = true;
    a = go(&m, x); b = go(&m, x);
    CHECK(a.last_gasp && has_frame(&a, SM_FRAME_LAST_GASP, 3) && !b.last_gasp);
    sm_init(&m, NULL);
    x = in(); x.supply_fault = true;
    CHECK(go(&m, x).last_gasp);
}

static void test_survival(void)
{
    sm_machine_t m; sm_inputs_t x = gas(); sm_output_t o;
    sm_init(&m, NULL);
    x.battery_low = true;
    CHECK(go(&m, x).state == SM_NORMAL);
    x = in(); x.battery_low = true; x.flame = true;
    go(&m, x);
    o = go(&m, x);
    CHECK(o.state == SM_SUSPICION && !o.camera_on);
}

static void test_frames(void)
{
    sm_machine_t m; sm_output_t o; int i, quiet = 1;
    sm_init(&m, NULL);
    for (i = 0; i < 19; i++) if (go(&m, in()).n_frames) quiet = 0;
    CHECK(quiet);
    o = go(&m, in());
    CHECK(o.n_frames == 1 && o.frames[0].kind == SM_FRAME_HEARTBEAT && o.frames[0].repeats == 1);
    o = go(&m, gas());
    CHECK(o.n_frames == 1 && o.frames[0].kind == SM_FRAME_STATE_CHANGE);
}

static void test_reasons_clear(void)
{
    sm_machine_t m; sm_output_t o; int i;
    to_suspicion(&m);
    for (i = 0; i < 10; i++) o = go(&m, in());
    CHECK(o.state == SM_NORMAL && o.reasons == 0);
}

static void test_first_flame_read_shortens_sleep(void)
{
    sm_machine_t m; sm_inputs_t x = in(), f = in(), a = in(), b = in(); sm_output_t o;
    sm_config_t c;
    f.flame = true;
    sm_init(&m, NULL);
    CHECK(go(&m, x).interval_s == 300.0);
    o = go(&m, f);
    CHECK(o.state == SM_NORMAL && o.interval_s == 30.0);
    CHECK(go(&m, x).interval_s == 300.0);                              /* unconfirmed read: back to Eco */
    CHECK(go(&m, f).interval_s == 30.0);
    CHECK(go(&m, f).state == SM_SUSPICION);
    sm_init(&m, NULL); a.flame = true; a.fwi_mode = SM_FWI_ALERT;
    CHECK(go(&m, a).interval_s == 30.0);                              /* never lengthens */
    sm_config_default(&c); c.flame_recheck_s = 0.0; sm_init(&m, &c);
    CHECK(go(&m, f).interval_s == 300.0);                             /* switched off */
    sm_config_default(&c); c.flame_recheck_s = 10.0; sm_init(&m, &c);
    CHECK(go(&m, a).interval_s == 10.0);
    sm_init(&m, NULL); b.flame = true; b.battery_low = true;
    CHECK(go(&m, b).interval_s == 30.0);                              /* Survival: one short extra wake */
}

static void test_bad_arguments(void)
{
    sm_machine_t m; sm_inputs_t x = in(); sm_output_t o;
    sm_init(&m, NULL);
    CHECK(sm_step(&m, NULL, &o) == -1 && sm_step(&m, &x, NULL) == -1);
    x.dt_s = -1.0; CHECK(sm_step(&m, &x, &o) == -1);
    x.dt_s = 1.0 / 0.0; CHECK(sm_step(&m, &x, &o) == -1);
    CHECK(m.since_frame_s == 0.0);                                  /* rejected calls left no trace */
}

static void test_frames_never_overflow(void)
{
    sm_machine_t m; sm_inputs_t x = gas(); sm_output_t o;
    sm_init(&m, NULL);
    x.housing_hot = true; x.dt_s = 700.0;
    cam(&x, SM_CAM_FIRE, 0.9);
    go(&m, x);
    o = go(&m, x);
    CHECK(o.n_frames <= SM_MAX_FRAMES);
}

int main(void)
{
    test_start_normal(); test_intervals(); test_gas_starts_suspicion(); test_flame_needs_two_reads();
    test_camera_confirms(); test_weak_or_background_camera(); test_gas_and_flame(); test_second_witness();
    test_clears(); test_trigger_resets_clear_counter(); test_fire_latched(); test_trigger_inside_fire_restarts_hold();
    test_camera_period(); test_pump(); test_last_gasp(); test_survival(); test_frames(); test_reasons_clear();
    test_first_flame_read_shortens_sleep(); test_bad_arguments(); test_frames_never_overflow();
    printf("%d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
