#ifndef GPS_UART_H
#define GPS_UART_H
#include <stdbool.h>
#include <stdint.h>
#include "ffp.h"
bool gps_uart_init(void);
/* Reads NMEA lines for up to timeout_ms; true when a position was obtained (unix_s = -1 if no valid time yet). */
bool gps_uart_poll(ffp_pos_t *pos, int64_t *unix_s, uint32_t timeout_ms);
#endif
