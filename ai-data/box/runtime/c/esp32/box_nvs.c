/* ESP-IDF adapter. NOT compiled or run in this repository (no ESP-IDF toolchain, no board yet). */
#include "box_nvs.h"

#include "nvs.h"

#define NS "box"

static int kv_read(void *ctx, const char *key, uint8_t *buf, size_t len)
{
    nvs_handle_t h;
    size_t n = len;
    esp_err_t err;
    (void)ctx;
    if (nvs_open(NS, NVS_READONLY, &h) != ESP_OK) return -1;       /* first boot: the namespace does not exist yet */
    err = nvs_get_blob(h, key, buf, &n);
    nvs_close(h);
    return err == ESP_OK ? (int)n : -1;
}

static int kv_write(void *ctx, const char *key, const uint8_t *buf, size_t len)
{
    nvs_handle_t h;
    esp_err_t err;
    (void)ctx;
    if (nvs_open(NS, NVS_READWRITE, &h) != ESP_OK) return -1;
    err = nvs_set_blob(h, key, buf, len);
    if (err == ESP_OK) err = nvs_commit(h);
    nvs_close(h);
    return err == ESP_OK ? 0 : -1;
}

const box_kv_t box_nvs_kv = { kv_read, kv_write, NULL };
