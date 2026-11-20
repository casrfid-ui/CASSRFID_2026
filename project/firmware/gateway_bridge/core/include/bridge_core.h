/* Gateway bridge (the ESP32 next to the RA-02 and the SIM800L). It owns the parts that must keep working when the SBC is
 * off, booting or crashed: it acknowledges every box frame within ~100 ms, keeps frames until the SBC can take them,
 * powers the SBC on when something matters, delivers the SBC's commands to the boxes in their listening window, and
 * sends an emergency SMS itself when a fire alert is not taken over by the SBC in time (spec 3.4: "alerts do not depend on one path").
 * C99, no heap, no OS. All hardware goes through bridge_hal_t (ESP32: ../main, host tests: ../host). */
#ifndef BRIDGE_CORE_H
#define BRIDGE_CORE_H

#include <stdbool.h>
#include <stdint.h>

#include "ffp.h"
#include "hdlc.h"

#ifdef __cplusplus
extern "C" {
#endif

#define BR_PEND_MAX 32
#define BR_CMDQ 4
#define BR_NUMBERS 4
#define BR_NUMBER_LEN 21
#define BR_SEEN 32

typedef struct {
    void *ctx;
    uint32_t (*now_ms)(void *ctx);
    void (*delay_ms)(void *ctx, uint32_t ms);
    int (*radio_tx)(void *ctx, const uint8_t frame[FFP_FRAME_LEN]);
    int (*radio_rx)(void *ctx, uint8_t frame[FFP_FRAME_LEN], int *rssi_dbm, int *snr_x4, uint32_t timeout_ms);   /* 1 frame, 0 none */
    int (*sbc_write)(void *ctx, const uint8_t *buf, size_t len);
    int (*sbc_read)(void *ctx, uint8_t *buf, size_t cap);          /* non-blocking: bytes available now, 0 if none */
    void (*sbc_power)(void *ctx, bool on);
    /* Queues one SMS for the modem task (non-blocking). The result comes back through bridge_sms_done(). Returns 0 if queued. */
    int (*sms_submit)(void *ctx, uint16_t id, const char *number, const char *text);
} bridge_hal_t;

typedef struct {
    uint8_t gw_id;                     /* 8..11 */
    uint32_t ack_delay_ms;             /* let the box switch from TX to RX */
    uint32_t cmd_gap_ms;               /* between a box's ack and the commands that follow */
    uint32_t radio_poll_ms;            /* radio_rx timeout per poll */
    uint32_t sbc_silent_ms;            /* no message for this long: the SBC is declared down */
    uint32_t sbc_boot_wait_ms;         /* power-on to HELLO; after it the bridge power-cycles once */
    uint32_t sbc_off_delay_ms;         /* after BYE */
    uint32_t sbc_periodic_wake_ms;     /* wake the SBC for the slow path at least this often when frames are waiting (0 = never) */
    uint8_t sbc_wake_pending;          /* ... or when this many frames are waiting */
    uint32_t dispatch_timeout_ms;      /* fire alert not taken over by the SBC within this: send the SMS from here */
    uint32_t sms_rate_limit_ms;        /* per box */
    uint32_t status_period_ms;
    uint32_t cmd_max_age_ms;
} bridge_cfg_t;

typedef struct { uint8_t bytes[FFP_FRAME_LEN]; int8_t rssi, snr; bool priority; } br_pending_t;
typedef struct { uint8_t bytes[FFP_FRAME_LEN]; uint8_t deliveries; uint32_t born_ms; } br_cmd_t;
typedef struct { bool active; uint8_t origin, seq, type; uint32_t deadline_ms; } br_armed_t;

typedef struct {
    bridge_cfg_t cfg;
    bridge_hal_t hal;
    hdlc_decoder_t dec;
    bool sbc_powered, sbc_up;
    uint32_t sbc_power_on_ms, sbc_last_rx_ms, sbc_bye_ms, last_periodic_ms, last_status_ms;
    bool sbc_cycled;
    br_pending_t pend[BR_PEND_MAX];
    uint8_t n_pend;
    br_cmd_t cmdq[8][BR_CMDQ];                 /* by box id */
    uint8_t n_cmd[8];
    br_armed_t armed[8];
    uint32_t last_sms_ms[8];
    bool sms_sent_once[8];
    ffp_status_t last_status[8];               /* status of the alert being watched, for the emergency text */
    uint8_t time_seq;
    ffp_pos_t pos[8];
    bool have_pos[8];
    uint8_t seen[BR_SEEN][3];
    uint8_t seen_pos;
    char numbers[BR_NUMBERS][BR_NUMBER_LEN];
    uint8_t n_numbers;
    uint8_t level;
    bool have_time;
    uint32_t time_unix_base;
    int8_t time_offset_q;
    uint32_t time_base_ms;
    uint16_t sms_counter;
    bool modem_ready;
    uint8_t csq;
    uint32_t frames_rx, acks_tx, crc_errors, forwarded, emergencies, sms_ok, sms_fail;
} bridge_t;

void bridge_cfg_default(bridge_cfg_t *c, uint8_t gw_id);
void bridge_init(bridge_t *b, const bridge_cfg_t *cfg, const bridge_hal_t *hal);
/* One pass: radio (blocks radio_poll_ms at most), SBC bytes, timers. Call in a loop. */
void bridge_poll(bridge_t *b);
/* Called by the modem task when an SMS finished (status = SIM_OK or SIM_E_*). */
void bridge_sms_done(bridge_t *b, uint16_t id, int status);
void bridge_set_modem_state(bridge_t *b, bool ready, uint8_t csq);

#ifdef __cplusplus
}
#endif
#endif
