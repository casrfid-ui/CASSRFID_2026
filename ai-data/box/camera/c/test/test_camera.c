/* Unit tests with a mock of the hardware: quality, protocol, session paths, power-off on every path. */
#include <stdio.h>
#include <string.h>
#include <math.h>
#include "box_camera.h"

static int checks = 0, fails = 0;
#define CHECK(c) do { checks++; if (!(c)) { fails++; printf("FAIL %s:%d  %s\n", __FILE__, __LINE__, #c); } } while (0)

/* ---------- mock ---------- */
typedef struct {
    bool power_state, wifi_state;
    int power_on_calls, power_off_calls, wifi_on_calls, wifi_off_calls;
    int fail_power, fail_luma_at, fail_jpeg, fail_wifi;
    int luma_calls, post_calls;
    int luma_kind;                 /* 0 good, 1 dark, 2 uniform, 3 saturated, 4 blurry */
    int post_rc[4]; int post_http[4]; const char *post_body[4];
    uint32_t now, post_cost, luma_cost, wifi_cost;
    uint32_t last_timeout;
    char last_headers[CAM_HEADERS_MAX]; size_t last_len;
} mock_t;

static void fill(uint8_t *b, int kind)
{
    int x, y;
    for (y = 0; y < 60; y++) for (x = 0; x < 80; x++) {
        uint8_t v;
        switch (kind) {
        case 1: v = (uint8_t)((x * 7 + y * 3) % 6); break;                 /* dark, texture */
        case 2: v = 128; break;                                            /* uniform */
        case 3: v = (uint8_t)(((x + y) & 1) ? 255 : 252); break;           /* saturated */
        case 4: v = (uint8_t)(60 + (x + y) * 7 / 10); break;                  /* smooth ramp: blurry */
        default: v = (uint8_t)(((x / 5 + y / 5) & 1) ? 200 : 60); break;   /* checker */
        }
        b[y * 80 + x] = v;
    }
}
static int h_power(void *c, bool on) { mock_t *m = c; if (on) { m->power_on_calls++; if (m->fail_power) return -1; m->power_state = true; } else { m->power_off_calls++; m->power_state = false; } return 0; }
static int h_luma(void *c, uint8_t *b, size_t cap, int *w, int *h)
{ mock_t *m = c; (void)cap; m->luma_calls++; m->now += m->luma_cost; if (m->fail_luma_at && m->luma_calls == m->fail_luma_at) return -1; fill(b, m->luma_kind); *w = 80; *h = 60; return 0; }
static int h_jpeg(void *c, uint8_t *b, size_t cap, size_t *len) { mock_t *m = c; (void)cap; if (m->fail_jpeg) return -1; memset(b, 0xAB, 1000); *len = 1000; return 0; }
static int h_wifi(void *c, bool on, uint32_t t) { mock_t *m = c; (void)t; if (on) { m->wifi_on_calls++; m->now += m->wifi_cost; if (m->fail_wifi) return -1; m->wifi_state = true; } else { m->wifi_off_calls++; m->wifi_state = false; } return 0; }
static int h_post(void *c, const cam_request_t *rq, char *resp, size_t cap, uint32_t tmo, int *http)
{
    mock_t *m = c; int i = m->post_calls++ < 4 ? m->post_calls - 1 : 3;
    m->last_timeout = tmo; m->last_len = rq->jpeg_len; strcpy(m->last_headers, rq->headers);
    m->now += m->post_cost;
    *http = m->post_http[i];
    if (m->post_body[i]) { strncpy(resp, m->post_body[i], cap - 1); resp[cap - 1] = '\0'; }
    return m->post_rc[i];
}
static uint32_t h_now(void *c) { return ((mock_t *)c)->now; }
static void h_delay(void *c, uint32_t ms) { ((mock_t *)c)->now += ms; }

static void hw_of(mock_t *m, cam_hw_t *hw)
{ hw->ctx = m; hw->power = h_power; hw->grab_luma = h_luma; hw->grab_jpeg = h_jpeg; hw->wifi = h_wifi; hw->post = h_post; hw->now_ms = h_now; hw->delay_ms = h_delay; }

static const char *GOOD = "{\"v\":1,\"id\":7,\"label\":\"fire\",\"conf\":0.934,\"ms\":210}";
static void mock_init(mock_t *m)
{ int i; memset(m, 0, sizeof *m); m->post_cost = 1000; m->luma_cost = 50; m->wifi_cost = 2000;
  for (i = 0; i < 4; i++) { m->post_http[i] = 200; m->post_body[i] = GOOD; } }

static cam_workspace_t WS; static uint8_t JPG[4096];
static int run(mock_t *m, const cam_config_t *cfg, cam_result_t *r)
{ cam_hw_t hw; cam_ids_t ids = { 3, 7, 1700000000LL, 5 }; hw_of(m, &hw); return cam_session_run(&hw, cfg, &ids, &WS, JPG, sizeof JPG, r); }
static void off_everywhere(const mock_t *m) { CHECK(!m->power_state); CHECK(!m->wifi_state); }

/* ---------- tests ---------- */
static void test_quality(void)
{
    uint8_t b[CAM_LUMA_MAX]; cam_config_t c; cam_quality_t q; int k;
    static const uint8_t want[5] = { 0, CAM_Q_DARK, CAM_Q_BLOCKED, CAM_Q_SATURATED, CAM_Q_BLURRY };
    cam_config_default(&c);
    for (k = 0; k < 5; k++) {
        fill(b, k);
        CHECK(cam_quality(b, 80, 60, &c, &q) == 0);
        if (k == 2) CHECK(q.flags & CAM_Q_BLOCKED);
        else if (k == 1) CHECK(q.flags & CAM_Q_DARK);
        else CHECK(q.flags == want[k] || (k == 3 && (q.flags & CAM_Q_SATURATED)));
    }
    fill(b, 0); cam_quality(b, 80, 60, &c, &q);
    CHECK(q.flags == 0); CHECK(fabs(q.mean - 130.0) < 1.0); CHECK(q.std > 60.0); CHECK(q.grad > 1.0);
    fill(b, 2); cam_quality(b, 80, 60, &c, &q);
    CHECK(q.mean == 128.0); CHECK(q.std == 0.0); CHECK(q.grad == 0.0); CHECK(!(q.flags & CAM_Q_BLURRY));   /* blocked, not blurry */
    CHECK(cam_quality(NULL, 80, 60, &c, &q) == -1); CHECK(cam_quality(b, 1, 60, &c, &q) == -1);
    CHECK(cam_quality(b, 200, 200, &c, &q) == -1);
}

static void test_protocol(void)
{
    uint8_t l; double cf; int ms; char hb[CAM_HEADERS_MAX]; cam_ids_t ids = { 3, 7, 1700000000LL, 5 };
    CHECK(cam_parse_response(GOOD, 7, &l, &cf, &ms) == 0); CHECK(l == CAM_LABEL_FIRE); CHECK(fabs(cf - 0.934) < 1e-12); CHECK(ms == 210);
    CHECK(cam_parse_response("{\"v\":1,\"id\":7,\"label\":\"smoke\",\"conf\":1}", 7, &l, &cf, &ms) == 0); CHECK(l == CAM_LABEL_SMOKE); CHECK(ms == -1);
    CHECK(cam_parse_response("{ \"v\" : 1 , \"id\" : 7 , \"label\" : \"background\" , \"conf\" : 0.0 }", 7, &l, &cf, &ms) == 0); CHECK(l == CAM_LABEL_BACKGROUND);
    CHECK(cam_parse_response(GOOD, 8, &l, &cf, &ms) == -2);                                  /* stale */
    CHECK(cam_parse_response("{\"v\":2,\"id\":7,\"label\":\"fire\",\"conf\":0.9}", 7, &l, &cf, &ms) == -1);
    CHECK(cam_parse_response("{\"id\":7,\"label\":\"fire\",\"conf\":0.9}", 7, &l, &cf, &ms) == -1);
    CHECK(cam_parse_response("{\"v\":1,\"id\":7,\"label\":\"cat\",\"conf\":0.9}", 7, &l, &cf, &ms) == -1);
    CHECK(cam_parse_response("{\"v\":1,\"id\":7,\"label\":\"fire\",\"conf\":1.5}", 7, &l, &cf, &ms) == -1);
    CHECK(cam_parse_response("{\"v\":1,\"id\":7,\"label\":\"fire\",\"conf\":-0.1}", 7, &l, &cf, &ms) == -1);
    CHECK(cam_parse_response("{\"v\":1,\"id\":7,\"label\":\"fire\"}", 7, &l, &cf, &ms) == -1);
    CHECK(cam_parse_response("{\"v\":1,\"id\":7,\"label\":\"fire", 7, &l, &cf, &ms) == -1);
    CHECK(cam_parse_response("{\"v\":1,\"id\":7,\"error\":\"decode\"}", 7, &l, &cf, &ms) == -3);
    CHECK(cam_parse_response("", 7, &l, &cf, &ms) == -1); CHECK(cam_parse_response(NULL, 7, &l, &cf, &ms) == -1);
    CHECK(cam_build_headers(hb, sizeof hb, &ids) > 0);
    CHECK(strstr(hb, "X-Box-Id: 3\r\n") && strstr(hb, "X-Req-Id: 7\r\n") && strstr(hb, "X-Time: 1700000000\r\n")
          && strstr(hb, "X-Reasons: 5\r\n") && strstr(hb, "Content-Type: image/jpeg\r\n"));
    CHECK(cam_build_headers(hb, 20, &ids) == -1);
}

static void test_session_paths(void)
{
    mock_t m; cam_config_t c; cam_result_t r;
    cam_config_default(&c);

    mock_init(&m); CHECK(run(&m, &c, &r) == 0);                                  /* success */
    CHECK(r.status == CAM_OK && r.valid && r.label == CAM_LABEL_FIRE && fabs(r.conf - 0.934) < 1e-12);
    CHECK(r.attempts == 1 && r.http_status == 200 && r.model_ms == 210);
    CHECK(m.luma_calls == c.warmup_frames + 1); CHECK(m.power_on_calls == 1 && m.power_off_calls == 1 && m.wifi_off_calls == 1);
    CHECK(strstr(m.last_headers, "X-Req-Id: 7")); CHECK(m.last_len == 1000); off_everywhere(&m);

    mock_init(&m); m.fail_power = 1; run(&m, &c, &r);                            /* power */
    CHECK(r.status == CAM_E_POWER && !r.valid && m.luma_calls == 0 && m.wifi_on_calls == 0); off_everywhere(&m);

    mock_init(&m); m.fail_luma_at = 2; run(&m, &c, &r);                          /* capture, in warm-up */
    CHECK(r.status == CAM_E_CAPTURE); CHECK(m.power_off_calls == 1); off_everywhere(&m);

    mock_init(&m); m.fail_jpeg = 1; run(&m, &c, &r);                             /* jpeg */
    CHECK(r.status == CAM_E_CAPTURE); CHECK(m.wifi_on_calls == 0); off_everywhere(&m);

    { int k; static const uint8_t f[4] = { CAM_Q_DARK, CAM_Q_BLOCKED, CAM_Q_SATURATED, CAM_Q_BLURRY };
      for (k = 1; k <= 4; k++) {                                                  /* quality refusals */
          mock_init(&m); m.luma_kind = k; run(&m, &c, &r);
          CHECK(r.status == CAM_E_QUALITY && !r.valid && (r.quality.flags & f[k - 1]));
          CHECK(m.wifi_on_calls == 0 && m.post_calls == 0); off_everywhere(&m);
      } }
    { cam_config_t d = c; d.upload_even_if_poor = true; mock_init(&m); m.luma_kind = 1; run(&m, &d, &r);
      CHECK(r.status == CAM_OK && (r.quality.flags & CAM_Q_DARK)); off_everywhere(&m); }

    mock_init(&m); m.fail_wifi = 1; run(&m, &c, &r);                             /* Wi-Fi fails: still switched off */
    CHECK(r.status == CAM_E_WIFI && m.post_calls == 0 && m.wifi_off_calls == 1); off_everywhere(&m);

    mock_init(&m); m.post_rc[0] = -1; m.post_body[0] = NULL; run(&m, &c, &r);    /* first post fails, retry succeeds */
    CHECK(r.status == CAM_OK && r.attempts == 2 && m.post_calls == 2); off_everywhere(&m);

    mock_init(&m); m.post_http[0] = 500; m.post_http[1] = 503; run(&m, &c, &r); /* both attempts non-200 */
    CHECK(r.status == CAM_E_HTTP && r.attempts == 2 && r.http_status == 503 && !r.valid); off_everywhere(&m);

    mock_init(&m); m.post_body[0] = m.post_body[1] = "{\"v\":1,\"id\":99,\"label\":\"fire\",\"conf\":0.9}"; run(&m, &c, &r);
    CHECK(r.status == CAM_E_RESPONSE && !r.valid && r.attempts == 2); off_everywhere(&m);                  /* stale id */

    mock_init(&m); m.post_body[0] = m.post_body[1] = "garbage"; run(&m, &c, &r);
    CHECK(r.status == CAM_E_RESPONSE); off_everywhere(&m);

    mock_init(&m); m.post_body[0] = "{\"v\":1,\"id\":7,\"error\":\"decode\"}"; run(&m, &c, &r);   /* error then good answer */
    CHECK(r.status == CAM_OK && r.attempts == 2); off_everywhere(&m);

    { cam_config_t d = c; d.session_budget_ms = 3000; mock_init(&m); run(&m, &d, &r);          /* budget: Wi-Fi alone costs 2 s */
      CHECK(r.status == CAM_OK || r.status == CAM_E_TIMEOUT); off_everywhere(&m); }
    { cam_config_t d = c; d.session_budget_ms = 2100; mock_init(&m); m.post_rc[0] = m.post_rc[1] = -1; run(&m, &d, &r);
      CHECK(r.status == CAM_E_HTTP || r.status == CAM_E_TIMEOUT); CHECK(m.last_timeout <= 2100); off_everywhere(&m); }
    { cam_config_t d = c; d.session_budget_ms = 100; mock_init(&m); run(&m, &d, &r);           /* budget gone during warm-up */
      CHECK(r.status == CAM_E_TIMEOUT && m.post_calls == 0); off_everywhere(&m); }
    { cam_config_t d = c; d.session_budget_ms = 20000; mock_init(&m); m.post_cost = 9000; m.post_rc[0] = m.post_rc[1] = -1; run(&m, &d, &r);
      CHECK(r.elapsed_ms <= 20000 + 9000 + 2000); CHECK(m.last_timeout <= 8000); off_everywhere(&m); }
    { cam_config_t d = c; d.post_timeout_ms = 8000; mock_init(&m); run(&m, &d, &r); CHECK(m.last_timeout == 8000); }

    { cam_hw_t hw; cam_ids_t ids = { 1, 1, 0, 0 }; mock_init(&m); hw_of(&m, &hw); hw.post = NULL;   /* arguments */
      CHECK(cam_session_run(&hw, &c, &ids, &WS, JPG, sizeof JPG, &r) == -1 && r.status == CAM_E_ARG && m.power_on_calls == 0);
      hw_of(&m, &hw); c.max_attempts = 0; CHECK(cam_session_run(&hw, &c, &ids, &WS, JPG, sizeof JPG, &r) == -1);
      CHECK(cam_session_run(&hw, &c, &ids, &WS, JPG, sizeof JPG, NULL) == -1); }
}

int main(void)
{
    test_quality(); test_protocol(); test_session_paths();
    printf("%d checks, %d failures\n", checks, fails);
    return fails ? 1 : 0;
}
