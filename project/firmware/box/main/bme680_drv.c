#include "bme680_drv.h"

#include "bme68x.h"
#include "esp_rom_sys.h"
#include "i2c_bus.h"
#include "pins.h"

const unsigned short BME_HEATER_C[GC_NSTEP] = { 100, 125, 150, 175, 200, 225, 250, 275, 300, 320 };
const unsigned short BME_HEATER_MS[GC_NSTEP] = { 150, 150, 150, 150, 150, 150, 150, 150, 150, 150 };

static struct bme68x_dev dev;
static uint8_t addr = I2C_BME680;

static BME68X_INTF_RET_TYPE rd(uint8_t reg, uint8_t *d, uint32_t n, void *p)
{
    (void)p;
    return i2c_bus_write_read(addr, &reg, 1, d, n) == ESP_OK ? BME68X_INTF_RET_SUCCESS : 1;
}

static BME68X_INTF_RET_TYPE wr(uint8_t reg, const uint8_t *d, uint32_t n, void *p)
{
    uint8_t buf[40];
    (void)p;
    if (n > sizeof buf - 1) return 1;
    buf[0] = reg;
    for (uint32_t i = 0; i < n; i++) buf[1 + i] = d[i];
    return i2c_bus_write(addr, buf, n + 1) == ESP_OK ? BME68X_INTF_RET_SUCCESS : 1;
}

static void dly(uint32_t us, void *p) { (void)p; esp_rom_delay_us(us); }

bool bme_init(void)
{
    struct bme68x_conf c;
    dev.intf = BME68X_I2C_INTF; dev.read = rd; dev.write = wr; dev.delay_us = dly; dev.amb_temp = 25; dev.intf_ptr = NULL;
    if (bme68x_init(&dev) != BME68X_OK) return false;
    c.os_hum = BME68X_OS_2X; c.os_pres = BME68X_OS_NONE; c.os_temp = BME68X_OS_4X; c.filter = BME68X_FILTER_OFF; c.odr = BME68X_ODR_NONE;
    return bme68x_set_conf(&c, &dev) == BME68X_OK;
}

static bool one(uint16_t heater_c, uint16_t heater_ms, bool gas, struct bme68x_data *out)
{
    struct bme68x_heatr_conf h = { .enable = gas ? BME68X_ENABLE : BME68X_DISABLE, .heatr_temp = heater_c, .heatr_dur = heater_ms };
    struct bme68x_conf c;
    uint8_t n = 0;
    uint32_t dur;
    bme68x_get_conf(&c, &dev);
    if (bme68x_set_heatr_conf(BME68X_FORCED_MODE, &h, &dev) != BME68X_OK) return false;
    if (bme68x_set_op_mode(BME68X_FORCED_MODE, &dev) != BME68X_OK) return false;
    dur = bme68x_get_meas_dur(BME68X_FORCED_MODE, &c, &dev) + (gas ? (uint32_t)heater_ms * 1000u : 0u);
    dev.delay_us(dur, dev.intf_ptr);
    if (bme68x_get_data(BME68X_FORCED_MODE, out, &n, &dev) != BME68X_OK || n == 0) return false;
    return !gas || (out->status & BME68X_GASM_VALID_MSK) != 0;
}

bool bme_read_env(double *t, double *rh)
{
    struct bme68x_data d;
    if (!one(300, 100, false, &d)) return false;
    *t = d.temperature; *rh = d.humidity;
    return true;
}

bool bme_scan(double g[GC_NSTEP], double t[GC_NSTEP], double rh[GC_NSTEP])
{
    int i;
    for (i = 0; i < GC_NSTEP; i++) {
        struct bme68x_data d;
        if (!one(BME_HEATER_C[i], BME_HEATER_MS[i], true, &d)) return false;
        g[i] = d.gas_resistance; t[i] = d.temperature; rh[i] = d.humidity;
    }
    return true;
}
