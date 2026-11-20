/* Unit tests of the C gas chain: every stage alone, then the chain. Mirrors python/tests (same cases). */
#include <math.h>
#include <stdio.h>
#include <string.h>
#include "gc_internal.h"

static int failures = 0, checks = 0;
#define CHECK(cond) do { checks++; if (!(cond)) { failures++; printf("FAIL line %d: %s\n", __LINE__, #cond); } } while (0)
#define NEAR(a, b, tol) CHECK(fabs((a) - (b)) <= (tol))

static gc_config_t cfg;

static void fill(double *v, double x) { int i; for (i = 0; i < GC_NSTEP; i++) v[i] = x; }

/* ---------- synthetic sensor: clean air, deterministic noise ---------- */
static unsigned rng_state = 12345u;
static double noise(double sd)           /* small zero-mean noise, uniform in [-sd*1.7, sd*1.7] */
{
    rng_state = rng_state * 1664525u + 1013904223u;
    return ((double)(rng_state >> 8) / 16777216.0 - 0.5) * 2.0 * sd * 1.7;
}
static void scan(double drop, double t, double h, double *gas, double *temp, double *rh)
{
    int i;
    for (i = 0; i < GC_NSTEP; i++) {
        gas[i] = exp(11.5 + 2.0 * i / 9.0 - drop + noise(0.01));
        temp[i] = t;
        rh[i] = h;
    }
}
static gc_result_t feed(gc_chain_t *c, double drop, double t, double h)
{
    double g[GC_NSTEP], tt[GC_NSTEP], hh[GC_NSTEP];
    gc_result_t r;
    scan(drop, t, h, g, tt, hh);
    CHECK(gc_update(c, g, tt, hh, 30.0, &r) == 0);
    return r;
}
static void ready(gc_chain_t *c)
{
    int i;
    gc_init(c, NULL);
    for (i = 0; i < 30; i++) feed(c, 0.0, 25.0, 50.0);
}

/* ---------- stages ---------- */
static void test_quality(void)
{
    double g[GC_NSTEP], t[GC_NSTEP], h[GC_NSTEP], p[GC_NSTEP];
    int same = 0, i;
    fill(g, 1e5); fill(t, 25.0); fill(h, 50.0);
    CHECK(gc_quality_flags(g, t, h, NULL, &same, &cfg) == 0);
    g[3] = 999.0; CHECK(gc_quality_flags(g, t, h, NULL, &same, &cfg) == GC_F_RANGE);
    g[3] = 120000001.0; CHECK(gc_quality_flags(g, t, h, NULL, &same, &cfg) == GC_F_RANGE);
    g[3] = 1000.0; CHECK(gc_quality_flags(g, t, h, NULL, &same, &cfg) == 0);          /* limits inclusive */
    g[3] = 120000000.0; CHECK(gc_quality_flags(g, t, h, NULL, &same, &cfg) == 0);
    g[3] = 102.4e6; CHECK(gc_quality_flags(g, t, h, NULL, &same, &cfg) == 0);         /* saturation is valid */
    g[3] = 1e5;
    t[9] = 86.0; CHECK(gc_quality_flags(g, t, h, NULL, &same, &cfg) == GC_F_RANGE);
    t[9] = -41.0; CHECK(gc_quality_flags(g, t, h, NULL, &same, &cfg) == GC_F_RANGE);
    t[9] = 25.0; h[0] = 101.0; CHECK(gc_quality_flags(g, t, h, NULL, &same, &cfg) == GC_F_RANGE);
    h[0] = -1.0; CHECK(gc_quality_flags(g, t, h, NULL, &same, &cfg) == GC_F_RANGE);
    h[0] = 50.0;
    g[0] = NAN; CHECK(gc_quality_flags(g, t, h, NULL, &same, &cfg) == GC_F_RANGE);
    g[0] = INFINITY; CHECK(gc_quality_flags(g, t, h, NULL, &same, &cfg) == GC_F_RANGE);
    g[0] = 1e5; t[2] = NAN; CHECK(gc_quality_flags(g, t, h, NULL, &same, &cfg) == GC_F_RANGE);
    t[2] = 25.0;
    /* stuck: 12 identical scans in a row */
    memcpy(p, g, sizeof p); same = 0;
    for (i = 1; i <= 11; i++) CHECK(gc_quality_flags(g, t, h, p, &same, &cfg) == 0);
    CHECK(gc_quality_flags(g, t, h, p, &same, &cfg) == GC_F_STUCK && same == 12);
    g[5] += 1.0;                                                                         /* a change resets the count */
    CHECK(gc_quality_flags(g, t, h, p, &same, &cfg) == 0 && same == 0);
}

static void test_compensation(void)
{
    double g[GC_NSTEP], t[GC_NSTEP], h[GC_NSTEP], o[GC_NSTEP];
    gc_config_t c = cfg;
    fill(g, 1e5); fill(t, 35.0); fill(h, 70.0);
    gc_compensate(g, t, h, &cfg, o);
    NEAR(o[0], log(1e5), 1e-15);                        /* plain ln by default */
    c.a_t = -0.02; c.b_h = -0.01; c.t_offset_c = 2.0;
    gc_compensate(g, t, h, &c, o);
    NEAR(o[4], log(1e5) + 0.02 * (33.0 - 25.0) + 0.01 * 20.0, 1e-12);
}

static void test_filter(void)
{
    double w[GC_MEDIAN_MAX][GC_NSTEP], m[GC_NSTEP], x[GC_NSTEP], out[GC_NSTEP], v[GC_NSTEP];
    int i;
    memset(w, 0, sizeof w);
    for (i = 0; i < 5; i++) fill(w[i], 10.0);
    fill(w[2], 99.0);                                   /* lone outlier */
    gc_window_median((const double (*)[GC_NSTEP])w, 5, m);
    NEAR(m[0], 10.0, 0);
    fill(w[0], 1.0); fill(w[1], 3.0);
    gc_window_median((const double (*)[GC_NSTEP])w, 2, m);   /* only the scans seen: median of 1 and 3 */
    NEAR(m[7], 2.0, 0);
    gc_window_median((const double (*)[GC_NSTEP])w, 1, m);
    NEAR(m[7], 1.0, 0);
    fill(w[0], 10.0); fill(w[1], 10.0); fill(w[2], 10.0);
    fill(x, 10.0); x[4] = 11.4;
    CHECK(!gc_is_spike(x, (const double (*)[GC_NSTEP])w, 3, 1.5));
    x[4] = 11.6;
    CHECK(gc_is_spike(x, (const double (*)[GC_NSTEP])w, 3, 1.5));
    CHECK(!gc_is_spike(x, (const double (*)[GC_NSTEP])w, 0, 1.5));   /* nothing seen yet */
    fill(x, 1.0); fill(v, 3.0);
    gc_smooth(NULL, v, 0.35, out); NEAR(out[0], 3.0, 0);
    gc_smooth(x, v, 0.35, out); NEAR(out[0], 1.0 + 0.35 * 2.0, 1e-15);
}

static void test_baseline_stages(void)
{
    double b[GC_NSTEP], e[GC_NSTEP];
    CHECK(!gc_learning_gate(6, 5, &cfg));               /* burn-in not over */
    CHECK(!gc_learning_gate(7, 4, &cfg));               /* window not full */
    CHECK(gc_learning_gate(7, 5, &cfg));
    CHECK(gc_baseline_may_follow(GC_NORMAL, 0.09, false, &cfg));
    CHECK(!gc_baseline_may_follow(GC_NORMAL, 0.10, false, &cfg));
    CHECK(!gc_baseline_may_follow(GC_SMOKE, 0.0, false, &cfg));
    CHECK(!gc_baseline_may_follow(GC_NORMAL, 0.0, true, &cfg));
    fill(b, 0.0); fill(e, 1.0);
    gc_baseline_follow(b, e, 6.0 * 3600.0, 6.0 * 3600.0);   /* dt = tau: 63.2 % of the way */
    NEAR(b[0], 1.0 - exp(-1.0), 1e-15);
    gc_baseline_follow(b, e, 1e9, 6.0 * 3600.0);            /* huge dt: reaches, never overshoots */
    CHECK(b[0] <= 1.0 && b[0] > 0.999999);
}

static void test_score_stages(void)
{
    double d[GC_NSTEP] = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10}, o[GC_NBANDS], c;
    int i;
    gc_band_depths(d, &cfg, o);
    NEAR(o[0], 2.5, 1e-15); NEAR(o[1], 6.0, 1e-15); NEAR(o[2], 9.0, 1e-15);
    NEAR(gc_instant_score(0.15, 0.30), 0.5, 1e-15);
    NEAR(gc_instant_score(-1.0, 0.30), 0.0, 0);
    NEAR(gc_instant_score(9.0, 0.30), 1.0, 0);
    c = gc_update_cusum(0.0, 0.13, &cfg); NEAR(c, 0.10, 1e-15);
    c = gc_update_cusum(c, 0.0, &cfg);    NEAR(c, 0.05, 1e-15);       /* halves when quiet */
    c = gc_update_cusum(c, 0.03, &cfg);   NEAR(c, 0.025, 1e-15);      /* depth == k does not accumulate */
    c = 0.0;
    for (i = 0; i < 50; i++) c = gc_update_cusum(c, 1.0, &cfg);
    NEAR(c, 1.5, 0);                                                 /* capped at 1.5 h */
}

static void test_class_stages(void)
{
    gc_config_t c = cfg;
    uint8_t cls = GC_NORMAL, cand = GC_NORMAL;
    int n = 0;
    CHECK(gc_wanted_class(0.39, 0.2, 5, GC_NORMAL, &cfg) == GC_NORMAL);
    CHECK(gc_wanted_class(0.40, 0.2, 5, GC_NORMAL, &cfg) == GC_SMOKE);
    CHECK(gc_wanted_class(0.30, 0.2, 5, GC_SMOKE, &cfg) == GC_SMOKE);     /* hysteresis */
    CHECK(gc_wanted_class(0.19, 0.2, 5, GC_SMOKE, &cfg) == GC_NORMAL);
    CHECK(gc_wanted_class(0.60, 0.03, 5, GC_SMOKE, &cfg) == GC_SMOKE);    /* CUSUM-only score keeps the state */
    CHECK(gc_wanted_class(0.60, 0.03, 5, GC_NORMAL, &cfg) == GC_SMOKE);
    CHECK(gc_wanted_class(0.60, 0.20, 0, GC_NORMAL, &cfg) == GC_SMOKE);   /* decoy off by default */
    c.decoy_enabled = true;
    CHECK(gc_wanted_class(0.60, 0.20, 2, GC_NORMAL, &c) == GC_DECOY);
    CHECK(gc_wanted_class(0.60, 0.20, 3, GC_NORMAL, &c) == GC_SMOKE);
    /* debounce: 2 scans to enter smoke, 3 to leave, fault at once, interrupted candidate restarts */
    gc_debounce(&cls, &cand, &n, GC_SMOKE, &cfg); CHECK(cls == GC_NORMAL && n == 1);
    gc_debounce(&cls, &cand, &n, GC_SMOKE, &cfg); CHECK(cls == GC_SMOKE && n == 0);
    gc_debounce(&cls, &cand, &n, GC_NORMAL, &cfg); gc_debounce(&cls, &cand, &n, GC_NORMAL, &cfg);
    CHECK(cls == GC_SMOKE);
    gc_debounce(&cls, &cand, &n, GC_NORMAL, &cfg); CHECK(cls == GC_NORMAL);
    gc_debounce(&cls, &cand, &n, GC_SMOKE, &cfg); gc_debounce(&cls, &cand, &n, GC_NORMAL, &cfg);
    gc_debounce(&cls, &cand, &n, GC_SMOKE, &cfg); CHECK(cls == GC_NORMAL && n == 1);
    gc_debounce(&cls, &cand, &n, GC_FAULT, &cfg); CHECK(cls == GC_FAULT);
}

/* ---------- chain ---------- */
static void test_clean_air_and_warmup(void)
{
    gc_chain_t c;
    gc_result_t r;
    int i, bad = 0;
    gc_init(&c, NULL);
    for (i = 0; i < 12; i++) { r = feed(&c, 0.0, 25.0, 50.0); CHECK(r.warmup && r.cls == GC_NORMAL && r.score == 0.0); }
    CHECK(!feed(&c, 0.0, 25.0, 50.0).warmup);                  /* 6 burn-in + 6 warm-up scans, ready on the 13th */
    for (i = 0; i < 500; i++) { r = feed(&c, 0.0, 25.0, 50.0); if (r.cls != GC_NORMAL || r.score > 0.2) bad++; }
    CHECK(bad == 0);
}

static void test_step_drop_then_recovery(void)
{
    gc_chain_t c; gc_result_t r; int i, first = -1;
    ready(&c);
    for (i = 0; i < 20; i++) { r = feed(&c, 0.4, 25.0, 50.0); if (first < 0 && r.cls == GC_SMOKE) first = i; }
    CHECK(first >= 0 && first <= 8 && r.cls == GC_SMOKE);      /* median of 5 + debounce delay the call a few scans */
    for (i = 0; i < 40; i++) r = feed(&c, 0.0, 25.0, 50.0);
    CHECK(r.cls == GC_NORMAL);
}

static void test_lone_spike_is_not_smoke(void)
{
    gc_chain_t c; gc_result_t r; int i;
    ready(&c);
    r = feed(&c, 2.0, 25.0, 50.0);
    CHECK(r.faults & GC_F_SPIKE);
    for (i = 0; i < 10; i++) { r = feed(&c, 0.0, 25.0, 50.0); CHECK(r.cls == GC_NORMAL); }
}

static void test_out_of_range_then_fault(void)
{
    gc_chain_t c; gc_result_t r; double g[GC_NSTEP], t[GC_NSTEP], h[GC_NSTEP];
    ready(&c);
    scan(0.0, 25.0, 50.0, g, t, h); g[2] = 5.0;
    gc_update(&c, g, t, h, 30.0, &r); CHECK(r.scan_bad && r.cls == GC_NORMAL && (r.faults & GC_F_RANGE));
    gc_update(&c, g, t, h, 30.0, &r); CHECK(r.scan_bad && r.cls == GC_NORMAL);
    gc_update(&c, g, t, h, 30.0, &r); CHECK(r.scan_bad && r.cls == GC_FAULT);
    r = feed(&c, 0.0, 25.0, 50.0); CHECK(!r.scan_bad);          /* good scans resume; fault releases after 3 */
    feed(&c, 0.0, 25.0, 50.0); r = feed(&c, 0.0, 25.0, 50.0);
    CHECK(r.cls == GC_NORMAL);
}

static void test_saturated_reading_valid(void)
{
    gc_chain_t c; gc_result_t r; double g[GC_NSTEP], t[GC_NSTEP], h[GC_NSTEP];
    ready(&c);
    scan(0.0, 25.0, 50.0, g, t, h); g[0] = 102.4e6;
    gc_update(&c, g, t, h, 30.0, &r);
    CHECK(!r.scan_bad);
}

static void test_stuck_sensor(void)
{
    gc_chain_t c; gc_result_t r; double g[GC_NSTEP], t[GC_NSTEP], h[GC_NSTEP]; int i;
    ready(&c);
    scan(0.0, 25.0, 50.0, g, t, h);
    for (i = 0; i < 12; i++) { gc_update(&c, g, t, h, 30.0, &r); CHECK(r.cls != GC_FAULT); }   /* first call differs from the previous scan */
    gc_update(&c, g, t, h, 30.0, &r);
    CHECK(r.cls == GC_FAULT && (r.faults & GC_F_STUCK));
}

static void test_baseline_frozen_in_smoke_and_follows_drift(void)
{
    gc_chain_t c; double b0[GC_NSTEP], b1[GC_NSTEP]; int i;
    ready(&c);
    for (i = 0; i < 10; i++) feed(&c, 0.4, 25.0, 50.0);
    gc_snapshot(&c, b0);
    for (i = 0; i < 20; i++) feed(&c, 0.4, 25.0, 50.0);
    gc_snapshot(&c, b1);
    for (i = 0; i < GC_NSTEP; i++) NEAR(b0[i], b1[i], 1e-9 + 0.0);     /* frozen while smoke is called */
    for (i = 0; i < 40; i++) feed(&c, 0.0, 25.0, 50.0);
    gc_snapshot(&c, b0);
    for (i = 0; i < 400; i++) feed(&c, 0.02, 25.0, 50.0);              /* small offset below the freeze score */
    gc_snapshot(&c, b1);
    CHECK(b1[0] < b0[0]);                                             /* the baseline moved toward the new level */
}

static void test_bands_localise(void)
{
    gc_chain_t c; gc_result_t r; double g[GC_NSTEP], t[GC_NSTEP], h[GC_NSTEP]; int i, k;
    ready(&c);
    for (k = 0; k < 10; k++) {
        scan(0.0, 25.0, 50.0, g, t, h);
        for (i = 7; i < 10; i++) g[i] *= exp(-0.5);                    /* only the high-temperature steps drop */
        gc_update(&c, g, t, h, 30.0, &r);
    }
    CHECK(r.bands[2] > 0.3 && r.bands[0] < 0.1 && r.peak_step >= 7);
}

static void test_restore_skips_warmup(void)
{
    gc_chain_t a, b; double base[GC_NSTEP]; gc_result_t r;
    ready(&a);
    gc_snapshot(&a, base);
    gc_init(&b, NULL);
    CHECK(!gc_snapshot(&b, base));                       /* nothing to save before the baseline exists */
    gc_restore(&b, base);
    r = feed(&b, 0.0, 25.0, 50.0);
    CHECK(!r.warmup);
}

static void test_decoy_never_by_default(void)
{
    gc_chain_t c; gc_result_t r; double g[GC_NSTEP], t[GC_NSTEP], h[GC_NSTEP]; int k;
    ready(&c);
    for (k = 0; k < 10; k++) {
        scan(0.0, 25.0, 50.0, g, t, h); g[0] *= exp(-0.8); g[1] *= exp(-0.8);
        gc_update(&c, g, t, h, 30.0, &r);
        CHECK(r.cls != GC_DECOY);
    }
}

static void test_inputs_not_modified_and_deterministic(void)
{
    gc_chain_t a, b; double g[GC_NSTEP], t[GC_NSTEP], h[GC_NSTEP], g2[GC_NSTEP], t2[GC_NSTEP], h2[GC_NSTEP];
    gc_result_t ra, rb; int i;
    gc_init(&a, NULL); gc_init(&b, NULL);
    for (i = 0; i < 60; i++) {
        scan(i > 30 ? 0.3 : 0.0, 25.0, 50.0, g, t, h);
        memcpy(g2, g, sizeof g); memcpy(t2, t, sizeof t); memcpy(h2, h, sizeof h);
        gc_update(&a, g, t, h, 30.0, &ra);
        CHECK(!memcmp(g, g2, sizeof g) && !memcmp(t, t2, sizeof t) && !memcmp(h, h2, sizeof h));
        gc_update(&b, g, t, h, 30.0, &rb);
        CHECK(ra.score == rb.score && ra.cls == rb.cls);
    }
}

static void test_slow_drift_above_k_over_tau_is_smoke(void)
{
    gc_chain_t c; gc_result_t r; int i, smoke = 0;
    ready(&c);
    for (i = 0; i < 400; i++) { r = feed(&c, 0.0012 * i, 25.0, 50.0); smoke |= r.cls == GC_SMOKE; }
    CHECK(smoke);
}

static void test_bad_arguments_and_config(void)
{
    gc_chain_t c; gc_result_t r; double g[GC_NSTEP], t[GC_NSTEP], h[GC_NSTEP]; gc_config_t bad = cfg;
    gc_init(&c, NULL);
    scan(0.0, 25.0, 50.0, g, t, h);
    CHECK(gc_update(&c, g, t, h, 0.0, &r) == -1);
    CHECK(gc_update(&c, g, t, h, NAN, &r) == -1);
    CHECK(gc_update(&c, NULL, t, h, 30.0, &r) == -1);
    CHECK(gc_update(&c, g, t, h, 30.0, &r) == 0 && c.scans == 1);   /* rejected calls left no trace */
    CHECK(gc_config_check(&cfg) == 0);
    bad.median_window = GC_MEDIAN_MAX + 1; CHECK(gc_init(&c, &bad) == -1);
    bad = cfg; bad.bands[1][1] = 11; CHECK(gc_config_check(&bad) == -1);
    bad = cfg; bad.tau_base_s = 0.0; CHECK(gc_config_check(&bad) == -1);
    bad = cfg; bad.smoke_off = 0.5; CHECK(gc_config_check(&bad) == -1);
}

static void test_other_window_sizes(void)
{
    gc_config_t c3 = cfg; gc_chain_t c; gc_result_t r; int i;
    c3.median_window = 3;
    gc_init(&c, &c3);
    for (i = 0; i < 30; i++) feed(&c, 0.0, 25.0, 50.0);
    r = feed(&c, 0.0, 25.0, 50.0);
    CHECK(!r.warmup);
}

int main(void)
{
    gc_config_default(&cfg);
    test_quality(); test_compensation(); test_filter(); test_baseline_stages(); test_score_stages(); test_class_stages();
    test_clean_air_and_warmup(); test_step_drop_then_recovery(); test_lone_spike_is_not_smoke();
    test_out_of_range_then_fault(); test_saturated_reading_valid(); test_stuck_sensor();
    test_baseline_frozen_in_smoke_and_follows_drift(); test_bands_localise(); test_restore_skips_warmup();
    test_decoy_never_by_default(); test_inputs_not_modified_and_deterministic();
    test_slow_drift_above_k_over_tau_is_smoke(); test_bad_arguments_and_config(); test_other_window_sizes();
    printf("%d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
