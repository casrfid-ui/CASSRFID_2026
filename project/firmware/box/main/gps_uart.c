#include "gps_uart.h"

#include <string.h>

#include "driver/uart.h"
#include "esp_timer.h"
#include "nmea.h"
#include "pins.h"

#define UART UART_NUM_0

bool gps_uart_init(void)
{
    uart_config_t c = { .baud_rate = 9600, .data_bits = UART_DATA_8_BITS, .parity = UART_PARITY_DISABLE, .stop_bits = UART_STOP_BITS_1,
                        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE, .source_clk = UART_SCLK_DEFAULT };
    if (uart_driver_install(UART, 512, 0, 0, NULL, 0) != ESP_OK) return false;
    if (uart_param_config(UART, &c) != ESP_OK) return false;
    return uart_set_pin(UART, PIN_GPS_TX, PIN_GPS_RX, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE) == ESP_OK;
}

bool gps_uart_poll(ffp_pos_t *pos, int64_t *unix_s, uint32_t timeout_ms)
{
    nmea_fix_t fix;
    char line[100];
    int n = 0;
    int64_t t0 = esp_timer_get_time();
    memset(&fix, 0, sizeof fix);
    uart_flush_input(UART);
    while ((esp_timer_get_time() - t0) / 1000 < timeout_ms && !(fix.have_pos && fix.have_time)) {
        uint8_t ch;
        if (uart_read_bytes(UART, &ch, 1, pdMS_TO_TICKS(50)) != 1) continue;
        if (ch == '$') n = 0;
        if (n < (int)sizeof line - 1) line[n++] = (char)ch;
        if (ch == '\n') { line[n] = 0; nmea_feed(&fix, line); n = 0; }
    }
    if (!fix.have_pos) return false;
    pos->lat_e7 = fix.lat_e7; pos->lon_e7 = fix.lon_e7; pos->alt_m = fix.alt_m; pos->sats = fix.sats; pos->fix = 1;
    *unix_s = fix.have_time ? fix.unix_s : -1;
    return true;
}
