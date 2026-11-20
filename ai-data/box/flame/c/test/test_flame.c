/* Unit tests of the C flame processing: the cases of python/tests/test_flame.py plus bad arguments. */
#include <stdio.h>
#include <string.h>
#include "flame.h"

static int failures = 0, checks = 0;
#define CHECK(cond) do { checks++; if (!(cond)) { failures++; printf("FAIL line %d: %s\n", __LINE__, #cond); } } while (0)

static fl_result_t run(const uint8_t *raw, int n, const fl_config_t *cfg)
{
    fl_result_t r;
    CHECK(fl_process(raw, n, cfg, &r) == 0);
    return r;
}

int main(void)
{
    uint8_t zeros[8] = {0}, ones[8] = {1, 1, 1, 1, 1, 1, 1, 1}, raw[FL_MAX_SAMPLES];
    fl_config_t c;
    fl_result_t r;
    int k;

    r = run(zeros, 8, NULL);
    CHECK(r.detected && r.ratio == 1.0 && r.transitions == 0 && r.n == 8);        /* active low: 0 is flame */
    r = run(ones, 8, NULL);
    CHECK(!r.detected && r.ratio == 0.0);

    fl_config_default(&c); c.active_low = false;
    CHECK(run(ones, 8, &c).detected && !run(zeros, 8, &c).detected);

    { uint8_t four[8] = {0, 0, 0, 0, 1, 1, 1, 1}, five[8] = {0, 0, 0, 0, 0, 1, 1, 1};
      CHECK(!run(four, 8, NULL).detected && run(five, 8, NULL).detected); }       /* limit: 5 of 8 */

    { uint8_t a[3] = {0, 0, 1}, b[3] = {0, 1, 1}, one0[1] = {0}, one1[1] = {1};
      CHECK(run(a, 3, NULL).detected && !run(b, 3, NULL).detected);
      CHECK(run(one0, 1, NULL).detected && !run(one1, 1, NULL).detected); }

    for (k = 0; k < 8; k++) { memcpy(raw, ones, 8); raw[k] = 0; CHECK(!run(raw, 8, NULL).detected); }   /* lone glitch */

    { uint8_t t[8] = {0, 1, 0, 1, 0, 0, 0, 0};
      CHECK(run(t, 8, NULL).transitions == 4); }
    fl_config_default(&c); c.flicker_min = 2;
    { uint8_t fl[8] = {0, 0, 1, 0, 0, 1, 0, 0};
      CHECK(!run(zeros, 8, &c).detected && run(fl, 8, &c).detected); }

    { uint8_t big[8] = {2, 5, 255, 1, 1, 1, 1, 1};
      CHECK(!run(big, 8, NULL).detected); }                                       /* non-zero = 1 */

    CHECK(fl_process(zeros, 0, NULL, &r) == -1);
    CHECK(fl_process(zeros, FL_MAX_SAMPLES + 1, NULL, &r) == -1);
    CHECK(fl_process(NULL, 8, NULL, &r) == -1 && fl_process(zeros, 8, NULL, NULL) == -1);
    memset(raw, 0, sizeof raw);
    CHECK(fl_process(raw, FL_MAX_SAMPLES, NULL, &r) == 0 && r.n == FL_MAX_SAMPLES);

    printf("%d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
