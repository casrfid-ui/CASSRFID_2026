/* SX1278 (RA-02) LoRa driver, register level, polled. Shared by the box and the gateway bridge (pins come from the caller). */
#ifndef SX127X_H
#define SX127X_H
#include <stdint.h>
#include "esp_err.h"

typedef struct {
    uint32_t freq_hz; int sf; int bw_khz; int cr; int tx_dbm; uint8_t sync_word;
    int pin_sck, pin_miso, pin_mosi, pin_nss;
    void (*reset)(int level);        /* drives the module's reset line (0 = reset); may be NULL if it is hard-wired */
} sx127x_cfg_t;

esp_err_t sx127x_init(const sx127x_cfg_t *cfg);       /* resets the module, checks the version register (0x12) */
esp_err_t sx127x_set_sf(int sf);
esp_err_t sx127x_send(const uint8_t *buf, int len, uint32_t timeout_ms);
/* 1 = frame (len bytes copied to buf, at most cap), 0 = timeout, < 0 = error. rssi in dBm, snr in 0.25 dB. */
int sx127x_receive(uint8_t *buf, int cap, int *rssi_dbm, int *snr_x4, uint32_t timeout_ms);
void sx127x_sleep(void);
#endif
