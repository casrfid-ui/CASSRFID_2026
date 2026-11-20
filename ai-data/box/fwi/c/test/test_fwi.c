/* Unit tests of the C port: defaults, 24 h history, persistence, corruption, input checks. */
#include <math.h>
#include <stdio.h>
#include <string.h>

#include "fwi.h"

static int failures = 0, checks = 0;
#define CHECK(cond) do { checks++; if (!(cond)) { failures++; printf("FAIL line %d: %s\n", __LINE__, #cond); } } while (0)

/* RAM-backed storage that stands for the board's flash */
typedef struct { uint8_t data[FWI_BLOB_SIZE]; int len; int writes; int fail_write; } ram_t;
static int ram_read(void *c, uint8_t *b, size_t n) { ram_t *r = c; if (r->len <= 0) return -1; if ((size_t)r->len < n) n = (size_t)r->len; memcpy(b, r->data, n); return (int)n; }
static int ram_write(void *c, const uint8_t *b, size_t n) { ram_t *r = c; if (r->fail_write) return -1; memcpy(r->data, b, n); r->len = (int)n; r->writes++; return 0; }

static fwi_input_t obs(int hour, double rain)
{
    fwi_input_t in = {0, 7, 30.0, 35.0, 12.0, 0.0};
    in.hour = hour % 24;
    in.rain_mm = rain;
    return in;
}

static void test_first_start_uses_defaults(void)
{
    fwi_engine_t e;
    int i;
    CHECK(fwi_engine_init(&e, NULL, NULL, NULL) == FWI_START_DEFAULTS);
    CHECK(e.state.ffmc == 85.0 && e.state.dmc == 6.0 && e.state.dc == 15.0);
    for (i = 0; i < FWI_RAIN_HOURS; i++) CHECK(e.state.rain_mm[i] == FWI_DEFAULT_RAIN_MM);
    CHECK(fwi_rain_24h(&e.state) == 0.0 && e.state.real_hours == 0);
}

static void test_provisional_until_24_real_hours(void)
{
    fwi_engine_t e;
    fwi_output_t o;
    int h;
    fwi_engine_init(&e, NULL, NULL, NULL);
    for (h = 0; h < 30; h++) {
        fwi_input_t in = obs(h, 0.0);
        CHECK(fwi_engine_update_hour(&e, &in, &o) == FWI_OK);
        if (h < 23) CHECK(o.provisional == 1 && o.history_hours == h + 1);
        else        CHECK(o.provisional == 0 && o.history_hours == 24);
    }
}

static void test_rain_window_is_24_hours(void)
{
    fwi_engine_t e;
    fwi_output_t o;
    fwi_input_t in;
    int h;
    fwi_engine_init(&e, NULL, NULL, NULL);
    in = obs(0, 20.0);
    fwi_engine_update_hour(&e, &in, &o);
    CHECK(fabs(fwi_rain_24h(&e.state) - 20.0) < 1e-12);
    for (h = 1; h < 24; h++) { in = obs(h, 0.0); fwi_engine_update_hour(&e, &in, &o); }
    CHECK(fabs(fwi_rain_24h(&e.state) - 20.0) < 1e-12);   /* hour 0 is still inside the window */
    in = obs(24, 0.0);
    fwi_engine_update_hour(&e, &in, &o);
    CHECK(fwi_rain_24h(&e.state) == 0.0);                 /* now it has left */
}

static void test_dmc_dc_only_move_at_noon(void)
{
    fwi_engine_t e;
    fwi_output_t o;
    int h;
    double dmc_prev, dc_prev;
    fwi_engine_init(&e, NULL, NULL, NULL);
    for (h = 0; h < 24; h++) {
        fwi_input_t in = obs(h, 0.0);
        dmc_prev = e.state.dmc; dc_prev = e.state.dc;
        fwi_engine_update_hour(&e, &in, &o);
        if (h == FWI_NOON_HOUR) CHECK(o.dmc > dmc_prev && o.dc > dc_prev);
        else                    CHECK(o.dmc == dmc_prev && o.dc == dc_prev);
    }
}

static void test_persistence_round_trip(void)
{
    ram_t flash; fwi_storage_t st;
    fwi_engine_t a, b, cont;
    fwi_output_t oa, ob, oc;
    int h;
    memset(&flash, 0, sizeof flash);
    st.read = ram_read; st.write = ram_write; st.ctx = &flash;
    fwi_engine_init(&cont, NULL, NULL, NULL);                     /* never restarted */
    CHECK(fwi_engine_init(&a, &st, NULL, NULL) == FWI_START_DEFAULTS);   /* empty flash */
    for (h = 0; h < 30; h++) {
        fwi_input_t in = obs(h, h == 5 ? 8.0 : 0.0);
        fwi_engine_update_hour(&a, &in, &oa);
        fwi_engine_update_hour(&cont, &in, &oc);
        CHECK(oa.saved == 1);
    }
    CHECK(flash.writes == 30);
    CHECK(fwi_engine_init(&b, &st, NULL, NULL) == FWI_START_RESTORED);   /* power cycle */
    {   /* codes + 24 h rain identical (compared through the serialised form: the struct has padding) */
        uint8_t ba[FWI_BLOB_SIZE], bb[FWI_BLOB_SIZE];
        fwi_state_pack(&a.state, ba); fwi_state_pack(&b.state, bb);
        CHECK(memcmp(ba, bb, sizeof ba) == 0);
    }
    for (h = 30; h < 60; h++) {
        fwi_input_t in = obs(h, 0.0);
        fwi_engine_update_hour(&b, &in, &ob);
        fwi_engine_update_hour(&cont, &in, &oc);
        CHECK(ob.fwi == oc.fwi && ob.dmc == oc.dmc && ob.dc == oc.dc && ob.history_hours == oc.history_hours);
    }
}

static void test_corrupt_or_foreign_blob_falls_back_to_defaults(void)
{
    ram_t flash; fwi_storage_t st;
    fwi_engine_t e;
    fwi_output_t o;
    fwi_input_t in = obs(3, 0.0);
    int bytes[] = {0, 5, 40, 100, 200, FWI_BLOB_SIZE - 1};
    unsigned i;
    memset(&flash, 0, sizeof flash);
    st.read = ram_read; st.write = ram_write; st.ctx = &flash;
    fwi_engine_init(&e, &st, NULL, NULL);
    fwi_engine_update_hour(&e, &in, &o);
    CHECK(fwi_engine_init(&e, &st, NULL, NULL) == FWI_START_RESTORED);
    for (i = 0; i < sizeof bytes / sizeof bytes[0]; i++) {
        uint8_t keep = flash.data[bytes[i]];
        flash.data[bytes[i]] ^= 0x5A;
        CHECK(fwi_engine_init(&e, &st, NULL, NULL) == FWI_START_DEFAULTS);
        CHECK(e.state.ffmc == 85.0 && e.state.real_hours == 0);
        flash.data[bytes[i]] = keep;
    }
    flash.len = FWI_BLOB_SIZE - 10;                                       /* truncated */
    CHECK(fwi_engine_init(&e, &st, NULL, NULL) == FWI_START_DEFAULTS);
}

static void test_write_failure_is_reported_not_fatal(void)
{
    ram_t flash; fwi_storage_t st;
    fwi_engine_t e;
    fwi_output_t o;
    fwi_input_t in = obs(1, 0.0);
    memset(&flash, 0, sizeof flash);
    flash.fail_write = 1;
    st.read = ram_read; st.write = ram_write; st.ctx = &flash;
    fwi_engine_init(&e, &st, NULL, NULL);
    CHECK(fwi_engine_update_hour(&e, &in, &o) == FWI_OK && o.saved == 0);
}

static void test_bad_input_leaves_state_untouched(void)
{
    fwi_engine_t e;
    fwi_output_t o;
    uint8_t before[FWI_BLOB_SIZE], after[FWI_BLOB_SIZE];
    fwi_input_t good = obs(4, 0.0), bad;
    fwi_engine_init(&e, NULL, NULL, NULL);
    fwi_engine_update_hour(&e, &good, &o);
    fwi_state_pack(&e.state, before);
    bad = good; bad.temp_c = NAN;        CHECK(fwi_engine_update_hour(&e, &bad, &o) == FWI_ERR_INPUT);
    bad = good; bad.rh_pct = -1.0;       CHECK(fwi_engine_update_hour(&e, &bad, &o) == FWI_ERR_INPUT);
    bad = good; bad.hour = 24;           CHECK(fwi_engine_update_hour(&e, &bad, &o) == FWI_ERR_INPUT);
    bad = good; bad.month = 0;           CHECK(fwi_engine_update_hour(&e, &bad, &o) == FWI_ERR_INPUT);
    bad = good; bad.rain_mm = INFINITY;  CHECK(fwi_engine_update_hour(&e, &bad, &o) == FWI_ERR_INPUT);
    fwi_state_pack(&e.state, after);
    CHECK(memcmp(before, after, sizeof before) == 0);
    CHECK(fwi_engine_update_hour(NULL, &good, &o) == FWI_ERR_ARG);
}

static void test_danger_and_mode(void)
{
    CHECK(fwi_danger_class(5.1) == 0 && fwi_danger_class(5.2) == 1 && fwi_danger_class(21.3) == 3);
    CHECK(fwi_danger_class(38.0) == 4 && fwi_danger_class(50.0) == 5 && fwi_danger_class(400.0) == 5);
    CHECK(fwi_mode_for_class(2) == FWI_MODE_ECO && fwi_mode_for_class(3) == FWI_MODE_ALERT);
}

int main(void)
{
    test_first_start_uses_defaults();
    test_provisional_until_24_real_hours();
    test_rain_window_is_24_hours();
    test_dmc_dc_only_move_at_noon();
    test_persistence_round_trip();
    test_corrupt_or_foreign_blob_falls_back_to_defaults();
    test_write_failure_is_reported_not_fatal();
    test_bad_input_leaves_state_untouched();
    test_danger_and_mode();
    printf("%d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
