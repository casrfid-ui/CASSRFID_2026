#include "cam_esp32.h"

#include <string.h>

#include "esp_camera.h"
#include "esp_event.h"
#include "esp_http_client.h"
#include "esp_netif.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/task.h"
#include "i2c_misc.h"
#include "pins.h"
#include "sdkconfig.h"

#define BIT_GOT_IP BIT0

static bool cam_up;
static EventGroupHandle_t evg;
static bool wifi_started, netif_ready;
static esp_netif_t *sta;

static camera_config_t cfg(pixformat_t fmt, framesize_t size)
{
    camera_config_t c = {
        .pin_pwdn = 32, .pin_reset = -1, .pin_xclk = 0, .pin_sccb_sda = 26, .pin_sccb_scl = 27,
        .pin_d7 = 35, .pin_d6 = 34, .pin_d5 = 39, .pin_d4 = 36, .pin_d3 = 21, .pin_d2 = 19, .pin_d1 = 18, .pin_d0 = 5,
        .pin_vsync = 25, .pin_href = 23, .pin_pclk = 22,
        .xclk_freq_hz = 20000000, .ledc_timer = LEDC_TIMER_0, .ledc_channel = LEDC_CHANNEL_0,
        .pixel_format = fmt, .frame_size = size, .jpeg_quality = 12, .fb_count = 1,
        .fb_location = CAMERA_FB_IN_PSRAM, .grab_mode = CAMERA_GRAB_WHEN_EMPTY,
    };
    return c;
}

static int hw_power(void *ctx, bool on)
{
    (void)ctx;
    if (on) {
        pcf_set(PCF_CAM_GATE, true);
        vTaskDelay(pdMS_TO_TICKS(150));
        return 0;
    }
    if (cam_up) { esp_camera_deinit(); cam_up = false; }
    pcf_set(PCF_CAM_GATE, false);
    return 0;
}

static int open_cam(pixformat_t fmt, framesize_t size)
{
    camera_config_t c = cfg(fmt, size);
    if (cam_up) { esp_camera_deinit(); cam_up = false; }
    if (esp_camera_init(&c) != ESP_OK) return -1;
    cam_up = true;
    return 0;
}

static int hw_luma(void *ctx, uint8_t *buf, size_t cap, int *w, int *h)
{
    camera_fb_t *fb;
    (void)ctx;
    if (open_cam(PIXFORMAT_GRAYSCALE, FRAMESIZE_QQVGA) != 0) return -1;
    fb = esp_camera_fb_get();
    if (!fb) return -1;
    if (fb->len > cap) { esp_camera_fb_return(fb); return -1; }
    memcpy(buf, fb->buf, fb->len);
    *w = fb->width; *h = fb->height;
    esp_camera_fb_return(fb);
    return 0;
}

static int hw_jpeg(void *ctx, uint8_t *buf, size_t cap, size_t *len)
{
    camera_fb_t *fb;
    (void)ctx;
    if (open_cam(PIXFORMAT_JPEG, FRAMESIZE_VGA) != 0) return -1;
    fb = esp_camera_fb_get();
    if (!fb) return -1;
    if (fb->len > cap) { esp_camera_fb_return(fb); return -1; }
    memcpy(buf, fb->buf, fb->len);
    *len = fb->len;
    esp_camera_fb_return(fb);
    return 0;
}

static void on_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    (void)arg; (void)data;
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) esp_wifi_connect();
    else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) esp_wifi_connect();
    else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) xEventGroupSetBits(evg, BIT_GOT_IP);
}

static int hw_wifi(void *ctx, bool on, uint32_t timeout_ms)
{
    (void)ctx;
    if (!on) {
        if (wifi_started) { esp_wifi_stop(); esp_wifi_deinit(); wifi_started = false; }
        return 0;
    }
    if (!netif_ready) {
        esp_netif_init();
        esp_event_loop_create_default();
        sta = esp_netif_create_default_wifi_sta();
        evg = xEventGroupCreate();
        esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, on_event, NULL);
        esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, on_event, NULL);
        netif_ready = true;
    }
    {
        wifi_init_config_t ic = WIFI_INIT_CONFIG_DEFAULT();
        wifi_config_t wc;
        memset(&wc, 0, sizeof wc);
        strncpy((char *)wc.sta.ssid, CONFIG_BOX_WIFI_SSID, sizeof wc.sta.ssid - 1);
        strncpy((char *)wc.sta.password, CONFIG_BOX_WIFI_PASS, sizeof wc.sta.password - 1);
        if (esp_wifi_init(&ic) != ESP_OK) return -1;
        esp_wifi_set_mode(WIFI_MODE_STA);
        esp_wifi_set_config(WIFI_IF_STA, &wc);
        xEventGroupClearBits(evg, BIT_GOT_IP);
        if (esp_wifi_start() != ESP_OK) return -1;
        wifi_started = true;
    }
    return (xEventGroupWaitBits(evg, BIT_GOT_IP, pdFALSE, pdTRUE, pdMS_TO_TICKS(timeout_ms)) & BIT_GOT_IP) ? 0 : -1;
}

typedef struct { char *buf; size_t cap, len; } sink_t;

static esp_err_t on_http(esp_http_client_event_t *e)
{
    if (e->event_id == HTTP_EVENT_ON_DATA) {
        sink_t *s = (sink_t *)e->user_data;
        size_t n = e->data_len;
        if (s->len + n >= s->cap) n = s->cap - 1 - s->len;
        memcpy(s->buf + s->len, e->data, n);
        s->len += n;
        s->buf[s->len] = 0;
    }
    return ESP_OK;
}

static int hw_post(void *ctx, const cam_request_t *rq, char *resp, size_t cap, uint32_t timeout_ms, int *http_status)
{
    sink_t s = { resp, cap, 0 };
    esp_http_client_config_t hc = { .url = CONFIG_BOX_GATEWAY_URL, .method = HTTP_METHOD_POST, .timeout_ms = (int)timeout_ms,
                                    .event_handler = on_http, .user_data = &s };
    esp_http_client_handle_t cl;
    char hdrs[CAM_HEADERS_MAX], *line, *save = NULL;
    esp_err_t e;
    (void)ctx;
    resp[0] = 0;
    cl = esp_http_client_init(&hc);
    if (!cl) return -1;
    strncpy(hdrs, rq->headers, sizeof hdrs - 1); hdrs[sizeof hdrs - 1] = 0;
    for (line = strtok_r(hdrs, "\r\n", &save); line; line = strtok_r(NULL, "\r\n", &save)) {
        char *colon = strchr(line, ':');
        if (!colon) continue;
        *colon = 0;
        esp_http_client_set_header(cl, line, colon + 2);
    }
    esp_http_client_set_post_field(cl, (const char *)rq->jpeg, (int)rq->jpeg_len);
    e = esp_http_client_perform(cl);
    *http_status = esp_http_client_get_status_code(cl);
    esp_http_client_cleanup(cl);
    return e == ESP_OK ? 0 : -1;
}

static uint32_t hw_now(void *ctx) { (void)ctx; return (uint32_t)(esp_timer_get_time() / 1000); }
static void hw_delay(void *ctx, uint32_t ms) { (void)ctx; vTaskDelay(pdMS_TO_TICKS(ms)); }

static const cam_hw_t HW = { NULL, hw_power, hw_luma, hw_jpeg, hw_wifi, hw_post, hw_now, hw_delay };

const cam_hw_t *cam_esp32_hw(void) { return &HW; }
