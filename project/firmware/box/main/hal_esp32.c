#include "hal_esp32.h"

#include <sys/time.h>

#include "bme680_drv.h"
#include "cam_esp32.h"
#include "esp_log.h"
#include "esp_random.h"
#include "esp_sleep.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "gps_uart.h"
#include "i2c_bus.h"
#include "i2c_misc.h"
#include "pins.h"
#include "sdkconfig.h"
#include "sx127x.h"

#define TAG "hal"
#define BATTERY_LOW_PCT 15
#define HOUSING_HOT_C 75.0

static box_hal_t H;
static bool bme_powered, bme_ok;
static int64_t t_wake_us;

static uint32_t h_now(void *c) { (void)c; return (uint32_t)((esp_timer_get_time() - t_wake_us) / 1000); }
static void h_delay(void *c, uint32_t ms) { (void)c; vTaskDelay(pdMS_TO_TICKS(ms)); }
static int64_t h_rtc(void *c) { struct timeval tv; (void)c; gettimeofday(&tv, NULL); return tv.tv_sec; }
static void h_rtc_set(void *c, int64_t u) { struct timeval tv = { .tv_sec = (time_t)u, .tv_usec = 0 }; (void)c; settimeofday(&tv, NULL); }
static uint32_t h_rand(void *c) { (void)c; return esp_random(); }

static void bme_power(bool on)
{
    if (on == bme_powered) return;
    pcf_set(PCF_GAS_GATE, on);
    bme_powered = on;
    if (on) { vTaskDelay(pdMS_TO_TICKS(30)); bme_ok = bme_init(); }
}

static bool h_env(void *c, double *t, double *rh) { (void)c; bme_power(true); return bme_ok && bme_read_env(t, rh); }
static void h_gas_power(void *c, bool on) { (void)c; if (on) bme_power(true); }               /* off at sleep time */
static bool h_scan(void *c, double g[GC_NSTEP], double t[GC_NSTEP], double rh[GC_NSTEP]) { (void)c; bme_power(true); return bme_ok && bme_scan(g, t, rh); }

static void h_flame(void *c, uint8_t raw[FL_MAX_SAMPLES], int n)
{
    int i;
    (void)c;
    for (i = 0; i < n; i++) {
        bool ok;
        raw[i] = pcf_get(PCF_FLAME_DO, &ok) ? 1 : 0;
        if (!ok) raw[i] = 1;                                   /* expander unreadable: no flame (the sensor fault shows in other ways) */
        vTaskDelay(pdMS_TO_TICKS(10));
    }
}

static void lora_reset(int level) { pcf_set(PCF_LORA_RST, level != 0); }

static int h_batt(void *c) { int p; double v; (void)c; return fuel_read(&p, &v) ? p : 50; }
static bool h_batt_low(void *c) { return h_batt(c) < BATTERY_LOW_PCT; }
static bool h_hot(void *c) { double t; (void)c; return lm75_read(&t) && t > HOUSING_HOT_C; }
static bool h_supply(void *c) { bool ok; bool lvl = pcf_get(PCF_SUPPLY_OK, &ok); (void)c; return ok && !lvl; }

static void h_gps_power(void *c, bool on) { (void)c; pcf_set(PCF_GPS_GATE, on); }
static bool h_gps_poll(void *c, ffp_pos_t *p, int64_t *u, uint32_t t) { (void)c; return gps_uart_poll(p, u, t); }
static void h_pump(void *c, bool on) { (void)c; pcf_set(PCF_PUMP, on); }
static const cam_hw_t *h_cam(void *c) { (void)c; return cam_esp32_hw(); }

static void h_sleep(void *c, double s)
{
    (void)c;
    pcf_set(PCF_GAS_GATE, false);
    pcf_set(PCF_GPS_GATE, false);
    pcf_set(PCF_CAM_GATE, false);
    sx127x_sleep();
    esp_sleep_enable_timer_wakeup((uint64_t)(s * 1e6));
    esp_deep_sleep_start();                                    /* the flame cannot wake the chip: it is behind the expander (spec 3.5) */
}

static int r_tx(void *c, const uint8_t f[FFP_FRAME_LEN]) { (void)c; return sx127x_send(f, FFP_FRAME_LEN, 3000) == ESP_OK ? 0 : -1; }
static int r_rx(void *c, uint8_t f[FFP_FRAME_LEN], int *rssi, int *snr, uint32_t t) { (void)c; return sx127x_receive(f, FFP_FRAME_LEN, rssi, snr, t); }
static int r_sf(void *c, int sf) { (void)c; return sx127x_set_sf(sf) == ESP_OK ? 0 : -1; }

const box_hal_t *hal_esp32_init(void)
{
    sx127x_cfg_t rc = { .freq_hz = CONFIG_BOX_LORA_FREQ_HZ, .sf = 9, .bw_khz = 125, .cr = 5, .tx_dbm = CONFIG_BOX_LORA_TX_DBM, .sync_word = 0x2F,
                     .pin_sck = PIN_LORA_SCK, .pin_miso = PIN_LORA_MISO, .pin_mosi = PIN_LORA_MOSI, .pin_nss = PIN_LORA_NSS, .reset = lora_reset };
    t_wake_us = esp_timer_get_time();
    if (i2c_bus_init() != ESP_OK || pcf_init() != ESP_OK) { ESP_LOGE(TAG, "I2C / expander"); return NULL; }
    gps_uart_init();
    if (sx127x_init(&rc) != ESP_OK) { ESP_LOGE(TAG, "radio not found"); return NULL; }
    H.ctx = NULL;
    H.now_ms = h_now; H.delay_ms = h_delay; H.rtc_unix_s = h_rtc; H.rtc_set_unix_s = h_rtc_set; H.random32 = h_rand;
    H.read_env = h_env; H.gas_power = h_gas_power; H.scan_gas = h_scan; H.flame_burst = h_flame;
    H.battery_pct = h_batt; H.battery_low = h_batt_low; H.housing_hot = h_hot; H.supply_fault = h_supply;
    H.gps_power = h_gps_power; H.gps_poll = h_gps_poll; H.pump = h_pump; H.camera_hw = h_cam; H.sleep_s = h_sleep;
    H.radio.ctx = NULL; H.radio.tx = r_tx; H.radio.rx = r_rx; H.radio.set_sf = r_sf;
    return &H;
}
