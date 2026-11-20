/* Radio rules of the box (spec 3.4 and figure 3): alert sent 3 times with priority, early stop on acknowledgement,
 * routine frames in a store-and-forward queue, relay of the other box's frames when no gateway answers,
 * downlink (ACK, CMD, TIME) collected for the application. C99, no heap. The state is plain data (keep it in RTC memory). */
#ifndef BOX_LINK_H
#define BOX_LINK_H

#include "box_hal.h"

#ifdef __cplusplus
extern "C" {
#endif

#define BOX_QN 16              /* routine queue length */
#define BOX_SEEN_N 16          /* de-duplication memory */
#define BOX_DL_MAX 4           /* downlink items kept per listen */

typedef struct {
    uint32_t alert_gap_ms;         /* between copies of an alert (also the ack wait) */
    uint32_t ack_wait_ms;          /* wait after a routine frame */
    uint32_t relay_wait_ms;        /* wait for a gateway ack before relaying a neighbour's frame */
    uint32_t gw_ok_window_s;       /* a gateway ack this recent means "gateway reachable" */
    uint8_t routine_tries;         /* sends per routine frame per wake-up before giving up until the next wake-up */
    uint8_t max_flush;             /* routine frames sent per wake-up at most */
} box_link_cfg_t;

typedef struct {
    uint8_t bytes[FFP_FRAME_LEN];
} box_qframe_t;

typedef struct {
    box_qframe_t q[BOX_QN];
    uint8_t n;                     /* queued routine frames, oldest first */
    uint8_t seq;                   /* next sequence number of this box */
    uint8_t seen[BOX_SEEN_N][3];   /* origin, seq, type */
    uint8_t seen_pos;
    int64_t last_gw_ack_unix;      /* 0 = never */
    uint32_t tx_count, rx_count, crc_errors, relayed_count, dropped_count;
} box_link_state_t;

typedef struct {
    uint8_t kind;                  /* FFP_T_ACK / FFP_T_CMD / FFP_T_TIME */
    int rssi_dbm, snr_x4;
    ffp_ack_t ack;
    ffp_cmd_t cmd;
    ffp_time_t time;
} box_downlink_t;

typedef struct {
    box_downlink_t items[BOX_DL_MAX];
    uint8_t n;
} box_downlinks_t;

typedef struct {
    box_link_cfg_t cfg;
    box_link_state_t *st;
    const box_hal_t *hal;
    uint8_t my_id;
    uint8_t other_id;              /* the other box, 0 = none (no relay) */
} box_link_t;

void box_link_cfg_default(box_link_cfg_t *c);
void box_link_state_init(box_link_state_t *s);
void box_link_init(box_link_t *l, const box_link_cfg_t *cfg, box_link_state_t *st, const box_hal_t *hal, uint8_t my_id, uint8_t other_id);

/* Sends a STATUS frame (ALERT, STATE or LAST_GASP: priority) `repeats` times, `alert_gap_ms` apart, listening for the
 * acknowledgement between copies; stops at the first ack for this sequence number. Downlink heard meanwhile goes to `dl`.
 * Returns the number of copies sent, and sets *acked. */
int box_link_send_priority(box_link_t *l, uint8_t type, uint8_t flags, const ffp_status_t *s, int repeats,
                           bool *acked, box_downlinks_t *dl, int64_t now_unix);

/* Routine frame (HEARTBEAT, TELEM, POS): assigned a sequence number and stored. Returns the sequence number. */
uint8_t box_link_queue_status(box_link_t *l, uint8_t type, uint8_t flags, const ffp_status_t *s);
uint8_t box_link_queue_telem(box_link_t *l, uint8_t flags, const ffp_telem_t *t);
uint8_t box_link_queue_pos(box_link_t *l, uint8_t flags, const ffp_pos_t *p);

/* Sends queued frames oldest first, waiting for the ack of each; pops acked frames; stops at the first frame that
 * stays unacknowledged. Returns the number of frames acknowledged. */
int box_link_flush(box_link_t *l, box_downlinks_t *dl, int64_t now_unix);

/* Listens for window_ms: collects downlink for this box, relays the other box's frames that no gateway acknowledged. */
void box_link_listen(box_link_t *l, uint32_t window_ms, box_downlinks_t *dl, int64_t now_unix);

bool box_link_gateway_reachable(const box_link_t *l, int64_t now_unix);

#ifdef __cplusplus
}
#endif
#endif
