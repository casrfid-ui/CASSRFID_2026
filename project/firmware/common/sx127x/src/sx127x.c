#include "sx127x.h"

#include "driver/spi_master.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#define REG_FIFO 0x00
#define REG_OPMODE 0x01
#define REG_FRF_MSB 0x06
#define REG_PA_CONFIG 0x09
#define REG_LNA 0x0C
#define REG_FIFO_ADDR_PTR 0x0D
#define REG_FIFO_TX_BASE 0x0E
#define REG_FIFO_RX_BASE 0x0F
#define REG_FIFO_RX_CURRENT 0x10
#define REG_IRQ_FLAGS 0x12
#define REG_RX_NB_BYTES 0x13
#define REG_PKT_SNR 0x19
#define REG_PKT_RSSI 0x1A
#define REG_MODEM_CONFIG1 0x1D
#define REG_MODEM_CONFIG2 0x1E
#define REG_PREAMBLE_MSB 0x20
#define REG_PAYLOAD_LEN 0x22
#define REG_MODEM_CONFIG3 0x26
#define REG_DETECT_OPT 0x31
#define REG_DETECT_THRESH 0x37
#define REG_SYNC_WORD 0x39
#define REG_VERSION 0x42
#define REG_PA_DAC 0x4D

#define MODE_LORA 0x80
#define MODE_SLEEP 0x00
#define MODE_STDBY 0x01
#define MODE_TX 0x03
#define MODE_RX_CONT 0x05

#define IRQ_RX_DONE 0x40
#define IRQ_CRC_ERR 0x20
#define IRQ_TX_DONE 0x08

static spi_device_handle_t dev;
static int cur_sf = 9, cur_bw = 125;

static uint8_t rd(uint8_t reg)
{
    uint8_t tx[2] = { reg & 0x7F, 0 }, rx[2] = { 0, 0 };
    spi_transaction_t t = { .length = 16, .tx_buffer = tx, .rx_buffer = rx };
    spi_device_polling_transmit(dev, &t);
    return rx[1];
}

static void wr(uint8_t reg, uint8_t v)
{
    uint8_t tx[2] = { reg | 0x80, v };
    spi_transaction_t t = { .length = 16, .tx_buffer = tx };
    spi_device_polling_transmit(dev, &t);
}

static void set_mode(uint8_t m) { wr(REG_OPMODE, MODE_LORA | m); }

static void modem(void)
{
    uint8_t bw_code = cur_bw >= 500 ? 9 : cur_bw >= 250 ? 8 : 7;            /* 125 kHz = 7 */
    uint8_t ldro = (cur_sf >= 11 && cur_bw <= 125) ? 1 : 0;                 /* low data rate optimise */
    wr(REG_MODEM_CONFIG1, (uint8_t)((bw_code << 4) | (1 << 1) | 0));        /* CR 4/5, explicit header */
    wr(REG_MODEM_CONFIG2, (uint8_t)((cur_sf << 4) | (1 << 2)));             /* CRC on */
    wr(REG_MODEM_CONFIG3, (uint8_t)((ldro << 3) | (1 << 2)));               /* AGC auto */
    wr(REG_DETECT_OPT, (uint8_t)((rd(REG_DETECT_OPT) & 0xF8) | (cur_sf == 6 ? 0x05 : 0x03)));
    wr(REG_DETECT_THRESH, cur_sf == 6 ? 0x0C : 0x0A);
}

esp_err_t sx127x_init(const sx127x_cfg_t *c)
{
    spi_bus_config_t bus = { .mosi_io_num = c->pin_mosi, .miso_io_num = c->pin_miso, .sclk_io_num = c->pin_sck,
                             .quadwp_io_num = -1, .quadhd_io_num = -1, .max_transfer_sz = 64 };
    spi_device_interface_config_t d = { .clock_speed_hz = 4000000, .mode = 0, .spics_io_num = c->pin_nss, .queue_size = 1 };
    uint32_t frf;
    esp_err_t e = spi_bus_initialize(SPI2_HOST, &bus, SPI_DMA_DISABLED);
    if (e != ESP_OK) return e;
    e = spi_bus_add_device(SPI2_HOST, &d, &dev);
    if (e != ESP_OK) return e;
    if (c->reset) { c->reset(0); vTaskDelay(pdMS_TO_TICKS(2)); c->reset(1); vTaskDelay(pdMS_TO_TICKS(10)); }
    if (rd(REG_VERSION) != 0x12) return ESP_ERR_NOT_FOUND;
    cur_sf = c->sf; cur_bw = c->bw_khz;
    set_mode(MODE_SLEEP);
    frf = (uint32_t)(((uint64_t)c->freq_hz << 19) / 32000000ULL);
    wr(REG_FRF_MSB, (uint8_t)(frf >> 16)); wr(REG_FRF_MSB + 1, (uint8_t)(frf >> 8)); wr(REG_FRF_MSB + 2, (uint8_t)frf);
    wr(REG_LNA, 0x23);
    wr(REG_PA_CONFIG, (uint8_t)(0x80 | ((c->tx_dbm > 17 ? 17 : c->tx_dbm) - 2)));     /* PA_BOOST */
    wr(REG_PA_DAC, 0x84);
    wr(REG_PREAMBLE_MSB, 0); wr(REG_PREAMBLE_MSB + 1, 8);
    wr(REG_SYNC_WORD, c->sync_word);
    wr(REG_FIFO_TX_BASE, 0); wr(REG_FIFO_RX_BASE, 0);
    modem();
    set_mode(MODE_STDBY);
    return ESP_OK;
}

esp_err_t sx127x_set_sf(int sf)
{
    if (sf < 7 || sf > 12) return ESP_ERR_INVALID_ARG;
    cur_sf = sf;
    set_mode(MODE_STDBY);
    modem();
    return ESP_OK;
}

esp_err_t sx127x_send(const uint8_t *buf, int len, uint32_t timeout_ms)
{
    int64_t t0 = esp_timer_get_time();
    int i;
    set_mode(MODE_STDBY);
    wr(REG_FIFO_ADDR_PTR, 0);
    for (i = 0; i < len; i++) wr(REG_FIFO, buf[i]);
    wr(REG_PAYLOAD_LEN, (uint8_t)len);
    wr(REG_IRQ_FLAGS, 0xFF);
    set_mode(MODE_TX);
    while (!(rd(REG_IRQ_FLAGS) & IRQ_TX_DONE)) {
        if ((esp_timer_get_time() - t0) / 1000 > timeout_ms) { set_mode(MODE_STDBY); return ESP_ERR_TIMEOUT; }
        vTaskDelay(1);
    }
    wr(REG_IRQ_FLAGS, IRQ_TX_DONE);
    set_mode(MODE_STDBY);
    return ESP_OK;
}

int sx127x_receive(uint8_t *buf, int cap, int *rssi_dbm, int *snr_x4, uint32_t timeout_ms)
{
    int64_t t0 = esp_timer_get_time();
    wr(REG_IRQ_FLAGS, 0xFF);
    set_mode(MODE_RX_CONT);
    for (;;) {
        uint8_t fl = rd(REG_IRQ_FLAGS);
        if (fl & IRQ_RX_DONE) {
            int n, i;
            wr(REG_IRQ_FLAGS, 0xFF);
            if (fl & IRQ_CRC_ERR) { set_mode(MODE_STDBY); return 0; }
            n = rd(REG_RX_NB_BYTES);
            wr(REG_FIFO_ADDR_PTR, rd(REG_FIFO_RX_CURRENT));
            for (i = 0; i < n && i < cap; i++) buf[i] = rd(REG_FIFO);
            *snr_x4 = (int8_t)rd(REG_PKT_SNR);                       /* already SNR x 4 */
            *rssi_dbm = -164 + rd(REG_PKT_RSSI);                     /* low-frequency port (433 MHz) */
            set_mode(MODE_STDBY);
            return n == cap ? 1 : 0;
        }
        if ((esp_timer_get_time() - t0) / 1000 >= timeout_ms) { set_mode(MODE_STDBY); return 0; }
        vTaskDelay(1);
    }
}

void sx127x_sleep(void) { set_mode(MODE_SLEEP); }
