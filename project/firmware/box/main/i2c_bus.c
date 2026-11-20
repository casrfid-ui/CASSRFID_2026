#include "i2c_bus.h"

#include "driver/i2c.h"
#include "pins.h"

#define PORT I2C_NUM_0
#define TMO pdMS_TO_TICKS(100)

esp_err_t i2c_bus_init(void)
{
    i2c_config_t c = {
        .mode = I2C_MODE_MASTER, .sda_io_num = PIN_I2C_SDA, .scl_io_num = PIN_I2C_SCL,
        .sda_pullup_en = GPIO_PULLUP_ENABLE, .scl_pullup_en = GPIO_PULLUP_ENABLE, .master.clk_speed = 100000,
    };
    esp_err_t e = i2c_param_config(PORT, &c);
    if (e != ESP_OK) return e;
    return i2c_driver_install(PORT, I2C_MODE_MASTER, 0, 0, 0);
}

esp_err_t i2c_bus_write(uint8_t addr, const uint8_t *d, size_t n) { return i2c_master_write_to_device(PORT, addr, d, n, TMO); }
esp_err_t i2c_bus_read(uint8_t addr, uint8_t *d, size_t n) { return i2c_master_read_from_device(PORT, addr, d, n, TMO); }
esp_err_t i2c_bus_write_read(uint8_t addr, const uint8_t *w, size_t wl, uint8_t *r, size_t rl)
{
    return i2c_master_write_read_device(PORT, addr, w, wl, r, rl, TMO);
}
