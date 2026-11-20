/* Box firmware entry point. Deep sleep restarts app_main at every wake-up, so one run is one wake-up:
 * restore (NVS + RTC memory) -> box_app_wake -> deep sleep. All the logic is in core/ (tested on the host). */
#include "box_app.h"
#include "box_nvs.h"
#include "esp_attr.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_sleep.h"
#include "hal_esp32.h"
#include "nvs_flash.h"
#include "sdkconfig.h"

#define TAG "box"

static RTC_DATA_ATTR box_retained_t retained;

void app_main(void)
{
    box_app_cfg_t cfg;
    const box_hal_t *hal;
    box_app_t *app;
    double sleep_s;

    if (nvs_flash_init() != ESP_OK) { nvs_flash_erase(); nvs_flash_init(); }
    hal = hal_esp32_init();
    if (!hal) {                                                       /* radio or I2C dead: retry in 5 min */
        esp_sleep_enable_timer_wakeup(300ULL * 1000000ULL);
        esp_deep_sleep_start();
    }
    box_app_cfg_default(&cfg, CONFIG_BOX_ID, CONFIG_BOX_OTHER_ID);
    cfg.rt.utc_offset_s = CONFIG_BOX_UTC_OFFSET_MIN * 60;
    cfg.static_lat_e7 = CONFIG_BOX_STATIC_LAT_E7;
    cfg.static_lon_e7 = CONFIG_BOX_STATIC_LON_E7;

    if (retained.magic != BOX_RET_MAGIC) box_retained_init(&retained, CONFIG_BOX_SIM_SEED);   /* power-on, not a deep-sleep wake */

    app = heap_caps_calloc(1, sizeof *app, MALLOC_CAP_SPIRAM);        /* camera workspace and JPEG buffer: 80 kB, in PSRAM */
    if (!app || box_app_init(app, &cfg, hal, &retained, &box_nvs_kv) != 0) {
        ESP_LOGE(TAG, "init failed");
        hal->sleep_s(NULL, 300.0);
    }
    sleep_s = box_app_wake(app);
    ESP_LOGI(TAG, "state=%d next wake in %.0f s", app->last_out.sm.state, sleep_s);
    hal->sleep_s(NULL, sleep_s);
}
