/* Gateway bridge firmware (ESP32 DevKit). Two tasks:
 *  - the bridge task polls the radio and the SBC UART (bridge_poll) and never blocks for long,
 *  - the modem task owns the SIM800L: SMS jobs are queued to it, results go back through bridge_sms_done().
 * Pins below are for a plain ESP32 DevKit; nothing here is shared with the box pin plan. NOT built or run in this repository. */
#include <string.h>

#include "bridge_core.h"
#include "driver/gpio.h"
#include "driver/uart.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "sdkconfig.h"
#include "sim800.h"
#include "sx127x.h"

#define TAG "bridge"
#define PIN_LORA_SCK 18
#define PIN_LORA_MISO 19
#define PIN_LORA_MOSI 23
#define PIN_LORA_NSS 5
#define PIN_LORA_RST 22
#define PIN_SBC_TX 17            /* UART1 to the SBC */
#define PIN_SBC_RX 16
#define PIN_SBC_POWER 4          /* gate of the SBC supply (high = on) */
#define PIN_SIM_TX 25            /* UART2 to the SIM800L */
#define PIN_SIM_RX 26
#define PIN_SIM_PWRKEY 27
#define SBC_UART UART_NUM_1
#define SIM_UART UART_NUM_2

typedef struct { uint16_t id; char number[BR_NUMBER_LEN]; char text[161]; } sms_job_t;

static bridge_t B;
static QueueHandle_t sms_q;
static SemaphoreHandle_t sbc_mutex;

static uint32_t h_now(void *c) { (void)c; return (uint32_t)(esp_timer_get_time() / 1000); }
static void h_delay(void *c, uint32_t ms) { (void)c; vTaskDelay(pdMS_TO_TICKS(ms)); }
static int h_rtx(void *c, const uint8_t f[16]) { (void)c; return sx127x_send(f, 16, 3000) == ESP_OK ? 0 : -1; }
static int h_rrx(void *c, uint8_t f[16], int *rssi, int *snr, uint32_t t) { (void)c; return sx127x_receive(f, 16, rssi, snr, t); }
static int h_sw(void *c, const uint8_t *b, size_t n)
{
    int r;
    (void)c;
    xSemaphoreTake(sbc_mutex, portMAX_DELAY);
    r = uart_write_bytes(SBC_UART, b, n);
    xSemaphoreGive(sbc_mutex);
    return r;
}
static int h_sr(void *c, uint8_t *b, size_t cap) { (void)c; return uart_read_bytes(SBC_UART, b, cap, 0); }
static void h_pw(void *c, bool on) { (void)c; gpio_set_level(PIN_SBC_POWER, on ? 1 : 0); }
static int h_sms(void *c, uint16_t id, const char *number, const char *text)
{
    sms_job_t j;
    (void)c;
    j.id = id;
    strncpy(j.number, number, sizeof j.number - 1); j.number[sizeof j.number - 1] = 0;
    strncpy(j.text, text, sizeof j.text - 1); j.text[sizeof j.text - 1] = 0;
    return xQueueSend(sms_q, &j, 0) == pdTRUE ? 0 : -1;
}

/* ---- SIM800L UART ---- */
static int sim_write(void *c, const uint8_t *b, size_t n) { (void)c; return uart_write_bytes(SIM_UART, b, n); }
static int sim_read_line(void *c, char *buf, size_t cap, uint32_t timeout_ms)
{
    size_t n = 0;
    int64_t t0 = esp_timer_get_time();
    (void)c;
    while ((esp_timer_get_time() - t0) / 1000 < timeout_ms) {
        uint8_t ch;
        if (uart_read_bytes(SIM_UART, &ch, 1, pdMS_TO_TICKS(20)) != 1) continue;
        if (ch == '>' && n == 0) { buf[0] = '>'; buf[1] = 0; return 1; }
        if (ch == '\r') continue;
        if (ch == '\n') { if (n == 0) continue; buf[n] = 0; return (int)n; }
        if (n < cap - 1) buf[n++] = (char)ch;
    }
    return 0;
}
static void sim_delay(void *c, uint32_t ms) { (void)c; vTaskDelay(pdMS_TO_TICKS(ms)); }

static void modem_task(void *arg)
{
    sim_io_t io = { NULL, sim_write, sim_read_line, sim_delay };
    sim800_t m;
    sms_job_t j;
    (void)arg;
    gpio_set_level(PIN_SIM_PWRKEY, 0); vTaskDelay(pdMS_TO_TICKS(1100)); gpio_set_level(PIN_SIM_PWRKEY, 1);   /* power-on pulse */
    vTaskDelay(pdMS_TO_TICKS(3000));
    for (;;) {
        int st = sim800_init(&m, &io);
        bridge_set_modem_state(&B, st == SIM_OK, (uint8_t)m.csq);
        if (st != SIM_OK) { ESP_LOGW(TAG, "modem init %d", st); vTaskDelay(pdMS_TO_TICKS(15000)); continue; }
        while (xQueueReceive(sms_q, &j, pdMS_TO_TICKS(60000)) == pdTRUE) {
            int r = sim800_send_sms(&m, j.number, j.text);
            if (r != SIM_OK) r = sim800_send_sms(&m, j.number, j.text);          /* one retry */
            bridge_sms_done(&B, j.id, r);
            if (r != SIM_OK) break;                                               /* re-initialise the modem */
        }
    }
}

static void bridge_task(void *arg)
{
    (void)arg;
    for (;;) bridge_poll(&B);
}

static void lora_reset(int level) { gpio_set_level(PIN_LORA_RST, level); }

static void load_numbers(bridge_t *b)
{
    const char *s = CONFIG_GW_EMERGENCY_NUMBERS;     /* "+216...;+216..." : same format as the SET_NUMBERS message of the SBC */
    size_t p, q = 0, n = strlen(s);
    b->n_numbers = 0;
    for (p = 0; p <= n && b->n_numbers < BR_NUMBERS; p++) {
        if (p == n || s[p] == ';') { if (q > 0) { b->numbers[b->n_numbers][q] = 0; b->n_numbers++; } q = 0; }
        else if (q < BR_NUMBER_LEN - 1) b->numbers[b->n_numbers][q++] = s[p];
    }
}

void app_main(void)
{
    bridge_cfg_t cfg;
    bridge_hal_t hal;
    sx127x_cfg_t rc = { .freq_hz = CONFIG_GW_LORA_FREQ_HZ, .sf = CONFIG_GW_SPREADING_FACTOR, .bw_khz = 125, .cr = 5, .tx_dbm = CONFIG_GW_LORA_TX_DBM,
                        .sync_word = 0x2F, .pin_sck = PIN_LORA_SCK, .pin_miso = PIN_LORA_MISO, .pin_mosi = PIN_LORA_MOSI, .pin_nss = PIN_LORA_NSS,
                        .reset = lora_reset };
    uart_config_t u = { .baud_rate = 115200, .data_bits = UART_DATA_8_BITS, .parity = UART_PARITY_DISABLE, .stop_bits = UART_STOP_BITS_1,
                        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE, .source_clk = UART_SCLK_DEFAULT };
    gpio_config_t out = { .pin_bit_mask = (1ULL << PIN_LORA_RST) | (1ULL << PIN_SBC_POWER) | (1ULL << PIN_SIM_PWRKEY), .mode = GPIO_MODE_OUTPUT };

    gpio_config(&out);
    gpio_set_level(PIN_SBC_POWER, 0);
    gpio_set_level(PIN_SIM_PWRKEY, 1);
    sbc_mutex = xSemaphoreCreateMutex();
    sms_q = xQueueCreate(8, sizeof(sms_job_t));

    uart_driver_install(SBC_UART, 1024, 1024, 0, NULL, 0);
    uart_param_config(SBC_UART, &u);
    uart_set_pin(SBC_UART, PIN_SBC_TX, PIN_SBC_RX, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);
    u.baud_rate = 9600;
    uart_driver_install(SIM_UART, 1024, 1024, 0, NULL, 0);
    uart_param_config(SIM_UART, &u);
    uart_set_pin(SIM_UART, PIN_SIM_TX, PIN_SIM_RX, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);

    if (sx127x_init(&rc) != ESP_OK) { ESP_LOGE(TAG, "radio not found"); for (;;) vTaskDelay(pdMS_TO_TICKS(60000)); }

    bridge_cfg_default(&cfg, CONFIG_GW_ID);
    hal.ctx = NULL; hal.now_ms = h_now; hal.delay_ms = h_delay; hal.radio_tx = h_rtx; hal.radio_rx = h_rrx;
    hal.sbc_write = h_sw; hal.sbc_read = h_sr; hal.sbc_power = h_pw; hal.sms_submit = h_sms;
    bridge_init(&B, &cfg, &hal);
    load_numbers(&B);

    xTaskCreate(modem_task, "modem", 6144, NULL, 4, NULL);
    xTaskCreate(bridge_task, "bridge", 6144, NULL, 6, NULL);
}
