#ifndef HAL_ESP32_H
#define HAL_ESP32_H
#include "box_hal.h"
/* Builds the HAL from the drivers. Initialises I2C, the expander, the BME680, the GPS UART and the radio. Returns NULL if the
 * radio is not found (nothing useful can be done then: the caller sleeps and retries). */
const box_hal_t *hal_esp32_init(void);
#endif
