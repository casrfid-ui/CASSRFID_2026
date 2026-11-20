/* Box application: one call per wake-up. Reads the board (box_hal.h), runs the ai-data runtime (FWI -> gas chain -> state
 * machine), builds the frames, applies the radio rules (box_link.h), applies the gateway's commands, runs the camera
 * session when the state machine asks for it, and returns the time to sleep. C99, no heap, no OS: the same code runs on the
 * ESP32 (../main) and in the host tests (../host). */
#ifndef BOX_APP_H
#define BOX_APP_H

#include "box_hal.h"
#include "box_link.h"
#include "box_runtime.h"
#include "box_wxsim.h"

#ifdef __cplusplus
extern "C" {
#endif

#define BOX_JPEG_MAX (60 * 1024)
#define BOX_RET_MAGIC 0xB0C5F1E1u

/* Survives deep sleep (RTC memory on the ESP32). Plain data. */
typedef struct {
    uint32_t magic;
    box_link_state_t link;
    box_wxsim_t wx;
    bool clock_synced;
    bool booted;
    ffp_pos_t pos;
    bool have_pos;
    int64_t last_pos_queued_unix;
    uint32_t cam_req_id;
    bool pending_camera;
    uint8_t pending_label;
    double pending_conf;
    uint8_t cam_status;            /* CAM_* of the last session */
    int64_t force_alert_until_unix;
    int64_t last_gps_unix;
    int64_t last_sync_req_unix;    /* while the clock is unsynchronised: a heartbeat asks the gateway for the time */
    uint8_t sf;
    uint8_t gw_alert_level;        /* from the last ack */
    uint32_t wake_count;
} box_retained_t;

typedef struct {
    uint8_t box_id, other_id;
    box_config_t rt;                       /* ai-data runtime configuration (gas chain, state machine, flame, UTC offset) */
    box_link_cfg_t link;
    int32_t static_lat_e7, static_lon_e7;  /* surveyed position used when there is no GPS fix (0 = unknown) */
    uint32_t gps_boot_timeout_ms;          /* first fix at boot */
    uint32_t gps_alert_timeout_ms;         /* refresh while the GPS is on in Suspicion / Fire */
    uint32_t rx_window_ms;                 /* listen after sending, for the ack and the commands that follow it */
    double alert_listen_s;                 /* in Suspicion / Fire: listen this long between scans (relay duty) */
    double pos_period_s;                   /* position frame period */
    double force_alert_default_ttl_s;      /* when a command carries no ttl */
    uint8_t default_sf;
} box_app_cfg_t;

typedef struct {
    box_app_cfg_t cfg;
    const box_hal_t *hal;
    box_retained_t *ret;
    box_runtime_t rt;
    box_link_t link;
    cam_workspace_t cam_ws;
    uint8_t cam_jpeg[BOX_JPEG_MAX];
    /* what the last wake-up did, for the host tests and for logging */
    box_tick_t last_tick;
    box_output_t last_out;
    int last_priority_sent;
    bool last_priority_acked;
    int last_flushed;
    int last_dl;
    bool last_camera_run;
    int restored_mask;
} box_app_t;

void box_app_cfg_default(box_app_cfg_t *c, uint8_t box_id, uint8_t other_id);
void box_retained_init(box_retained_t *r, uint32_t seed);

/* ret must outlive the app (RTC memory). kv may be NULL (no persistence). Returns 0, or -1 for a bad configuration. */
int box_app_init(box_app_t *a, const box_app_cfg_t *cfg, const box_hal_t *hal, box_retained_t *ret, const box_kv_t *kv);

/* One wake-up. Returns the seconds to sleep before the next one. */
double box_app_wake(box_app_t *a);

#ifdef __cplusplus
}
#endif
#endif
