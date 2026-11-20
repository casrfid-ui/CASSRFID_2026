/* ESP-IDF adapter. NOT compiled or run in this repository (no ESP-IDF toolchain, no board yet):
 * to be built and tested with the firmware. The portable engine in src/fwi.c is what is tested. */
#include "fwi_nvs.h"

#include "nvs.h"

#define NS  "fwi"
#define KEY "state"

static int nvs_read_blob(void *ctx, uint8_t *buf, size_t len)
{
    nvs_handle_t h;
    size_t n = len;
    esp_err_t err;
    (void)ctx;
    if (nvs_open(NS, NVS_READONLY, &h) != ESP_OK) return -1;   /* first boot: namespace does not exist yet */
    err = nvs_get_blob(h, KEY, buf, &n);
    nvs_close(h);
    return err == ESP_OK ? (int)n : -1;
}

static int nvs_write_blob(void *ctx, const uint8_t *buf, size_t len)
{
    nvs_handle_t h;
    esp_err_t err;
    (void)ctx;
    if (nvs_open(NS, NVS_READWRITE, &h) != ESP_OK) return -1;
    err = nvs_set_blob(h, KEY, buf, len);
    if (err == ESP_OK) err = nvs_commit(h);
    nvs_close(h);
    return err == ESP_OK ? 0 : -1;
}

const fwi_storage_t fwi_nvs_storage = { nvs_read_blob, nvs_write_blob, NULL };
