/* Box runtime: one call per wake-up runs FWI (hourly) -> gas chain (per scan) -> state machine, and keeps the
 * flash copies (FWI state, gas baseline, Fire latch) up to date. C99, no heap, no OS, no libc clock.
 * The application (ESP-IDF, see esp32/) reads the sensors, fills a box_tick_t, calls box_runtime_step, then acts on
 * the box_output_t: schedule the next wake-up, power the camera, build and send the frames, drive the pump. */
#ifndef BOX_RUNTIME_H
#define BOX_RUNTIME_H

#include "flame.h"
#include "fwi.h"
#include "gas_chain.h"
#include "state_machine.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Key-value store on the board's flash (NVS). Keys are at most 15 characters.
 * read: bytes read, or < 0 when the key does not exist. write: 0 on success, < 0 on failure. */
typedef struct {
    int (*read)(void *ctx, const char *key, uint8_t *buf, size_t len);
    int (*write)(void *ctx, const char *key, const uint8_t *buf, size_t len);
    void *ctx;
} box_kv_t;

#define BOX_KEY_FWI  "fwi"
#define BOX_KEY_GAS  "gas_base"
#define BOX_KEY_SM   "sm_state"
#define BOX_KEY_META "rt_meta"

typedef struct {
    int32_t utc_offset_s;            /* local time = UTC + offset; FWI uses local hour and month */
    double baseline_save_period_s;   /* gas baseline written to flash at most this often (and when first ready) */
    gc_config_t gas;
    sm_config_t sm;
    fl_config_t flame;
} box_config_t;

enum { BOX_RESTORED_FWI = 1, BOX_RESTORED_GAS = 2, BOX_RESTORED_SM = 4, BOX_RESTORED_META = 8 };

typedef struct {
    int64_t unix_s;                  /* RTC, UTC seconds */
    /* weather, read at every wake-up when available */
    bool weather_valid;
    double temp_c, rh_pct, wind_kmh;
    double rain_mm;                  /* rain since the previous wake-up (>= 0); accumulated until the next FWI hour */
    /* gas scan, only when one was performed at this wake-up */
    bool gas_valid;
    double gas_ohm[GC_NSTEP], gas_temp_c[GC_NSTEP], gas_rh_pct[GC_NSTEP];
    bool flame;                      /* already-processed flame read; used only when flame_n == 0 */
    uint8_t flame_raw[FL_MAX_SAMPLES];   /* burst of digital reads of the flame module */
    uint8_t flame_n;                 /* 0 = no burst: use `flame` */
    bool camera_valid;               /* a capture finished */
    uint8_t camera_label;            /* SM_CAM_* */
    double camera_conf;
    bool battery_low, housing_hot, supply_fault;
} box_tick_t;

typedef struct {
    sm_output_t sm;                  /* state, next interval, camera/GPS/pump, frames, last gasp, reasons */
    bool want_gas_scan;              /* false in Survival: do not power the gas sensor */
    bool fwi_updated;                /* an FWI hour was computed at this wake-up */
    int fwi_status;                  /* fwi_status_t of that update (FWI_OK, or the error that deferred it) */
    fwi_output_t fwi;                /* last known FWI values */
    bool gas_scanned;
    gc_result_t gas;                 /* result of this wake-up's scan, or the last one */
    bool flame_processed;            /* the flame burst was processed at this wake-up */
    int flame_status;                /* 0, or -1 when the burst was refused (then `flame` is used) */
    fl_result_t flame;               /* result of that burst */
    bool baseline_saved;
    bool clock_jump;                 /* unix_s went backwards: dt treated as 0 */
    int storage_errors;              /* failed flash writes at this wake-up */
} box_output_t;

typedef struct {
    box_config_t cfg;
    box_kv_t kv;
    fwi_storage_t fwi_store;
    fwi_engine_t fwi;
    gc_chain_t gas;
    sm_machine_t sm;
    fwi_output_t fwi_last;
    gc_result_t gas_last;
    bool have_last_unix, have_last_gas, have_fwi_hour, have_fwi_out;
    int64_t last_unix_s, last_gas_unix_s, last_fwi_hour, last_baseline_save_s;
    double rain_acc_mm;
    uint8_t saved_sm_state;
    bool saved_gasp;
    bool baseline_saved_once;
} box_runtime_t;

void box_config_default(box_config_t *cfg);

/* Restores whatever is in flash. kv may be NULL (no persistence). Returns a mask of BOX_RESTORED_*,
 * or -1 for a bad configuration. */
int box_runtime_init(box_runtime_t *rt, const box_config_t *cfg, const box_kv_t *kv);

/* One wake-up. Returns 0, or -1 for bad arguments (NULL, negative time); state untouched then. */
int box_runtime_step(box_runtime_t *rt, const box_tick_t *tick, box_output_t *out);

/* Operator or gateway acknowledgement: leave Fire (also clears the flash copy). */
void box_runtime_reset_fire(box_runtime_t *rt);

#ifdef __cplusplus
}
#endif
#endif
