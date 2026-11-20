/* Shared I2C bus: BME680, PCF8574, MAX17048, LM75. A mutex is not needed: everything runs in one task. */
#ifndef I2C_BUS_H
#define I2C_BUS_H
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"
esp_err_t i2c_bus_init(void);
esp_err_t i2c_bus_write(uint8_t addr, const uint8_t *data, size_t len);
esp_err_t i2c_bus_read(uint8_t addr, uint8_t *data, size_t len);
esp_err_t i2c_bus_write_read(uint8_t addr, const uint8_t *w, size_t wl, uint8_t *r, size_t rl);
#endif
