/* Scripted board for the host tests: simulated clock, radio with an optional automatic gateway, programmable sensors. */
#ifndef MOCK_HAL_H
#define MOCK_HAL_H

#include "box_hal.h"

#define MOCK_RXQ 48
#define MOCK_TXLOG 256

typedef struct { bool used; uint32_t at_ms; uint8_t w[FFP_FRAME_LEN]; int rssi; } mock_rx_t;

typedef struct {
    uint32_t ms;                       /* monotonic simulated time */
    int64_t base_unix;
    int64_t rtc_offset_s;              /* added by rtc_set_unix_s */
    bool rtc_set;
    /* radio */
    uint8_t tx_log[MOCK_TXLOG][FFP_FRAME_LEN];
    uint32_t tx_ms[MOCK_TXLOG];
    int n_tx;
    mock_rx_t rxq[MOCK_RXQ];
    bool gw_auto_ack;                  /* answer every ACK_REQ frame of a box with an ACK */
    int gw_ack_from_tx;                /* ... but only from the Nth transmission on (1-based) */
    bool gw_dead;
    uint8_t gw_id, gw_alert_level;
    int sf;
    /* sensors */
    double env_t, env_rh, gas_base, gas_scale;
    bool env_ok, gas_ok, flame_on, battery_low, housing_hot, supply_fault;
    int battery_pct;
    int gas_calls, flame_calls;
    bool gps_on, pump_on, gas_powered;
    bool gps_has_fix;
    ffp_pos_t gps_pos;
    int64_t gps_unix;
    uint32_t rng;
    /* camera */
    cam_hw_t cam;
    bool cam_present;
    int cam_runs;
    const char *cam_answer_label;
    double cam_answer_conf;
    uint32_t cam_last_id;
    box_hal_t hal;
} mock_t;

void mock_init(mock_t *m);
void mock_inject(mock_t *m, const ffp_frame_t *f, uint32_t at_ms);
int mock_count_tx(const mock_t *m, int type);
int mock_tx_decode(const mock_t *m, int i, ffp_frame_t *f);
#endif
