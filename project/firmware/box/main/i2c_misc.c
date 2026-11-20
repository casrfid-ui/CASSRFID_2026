#include "i2c_misc.h"

#include "i2c_bus.h"
#include "pins.h"

static uint8_t shadow = 0xFF;                /* quasi-bidirectional: 1 = input / released */

static esp_err_t pcf_push(void) { return i2c_bus_write(PCF_ADDR, &shadow, 1); }

esp_err_t pcf_init(void)
{
    shadow = 0xFF;
    shadow &= (uint8_t)~(1u << PCF_PUMP);                    /* relay off (drive low = off assumed; check the relay board polarity) */
    shadow &= (uint8_t)~(1u << PCF_CAM_GATE);
    shadow &= (uint8_t)~(1u << PCF_GPS_GATE);
    shadow &= (uint8_t)~(1u << PCF_GAS_GATE);
    return pcf_push();
}

void pcf_set(int bit, bool level)
{
    if (level) shadow |= (uint8_t)(1u << bit); else shadow &= (uint8_t)~(1u << bit);
    pcf_push();
}

bool pcf_get(int bit, bool *ok)
{
    uint8_t v = 0;
    esp_err_t e = i2c_bus_read(PCF_ADDR, &v, 1);
    if (ok) *ok = e == ESP_OK;
    return e == ESP_OK && (v & (1u << bit));
}

bool fuel_read(int *percent, double *volts)
{
    uint8_t r = 0x04, soc[2], vc[2];                          /* SOC register, then VCELL (0x02) */
    uint8_t rv = 0x02;
    if (i2c_bus_write_read(I2C_MAX17048, &r, 1, soc, 2) != ESP_OK) return false;
    if (i2c_bus_write_read(I2C_MAX17048, &rv, 1, vc, 2) != ESP_OK) return false;
    *percent = soc[0] > 100 ? 100 : soc[0];
    *volts = (double)(((uint16_t)vc[0] << 8) | vc[1]) * 78.125e-6;
    return true;
}

bool lm75_read(double *celsius)
{
    uint8_t r = 0x00, v[2];
    int16_t raw;
    if (i2c_bus_write_read(I2C_LM75, &r, 1, v, 2) != ESP_OK) return false;
    raw = (int16_t)(((uint16_t)v[0] << 8) | v[1]) >> 7;       /* 9-bit, 0.5 degC */
    *celsius = raw * 0.5;
    return true;
}
