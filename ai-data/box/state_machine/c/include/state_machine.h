/* Box state machine: Normal -> Suspicion -> Fire. One sm_step per wake-up.
 * C99, no heap, no I/O, no clock: the caller measures dt_s. Reference: ../python (same decisions, tested by parity).
 * sm_machine_t is plain data: keep it in RTC memory to survive deep sleep, or in flash to survive a reboot. */
#ifndef STATE_MACHINE_H
#define STATE_MACHINE_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

enum { SM_NORMAL = 0, SM_SUSPICION = 1, SM_FIRE = 2 };
enum { SM_R_GAS = 1, SM_R_FLAME = 2, SM_R_CAMERA = 4, SM_R_FWI = 8 };        /* reason bits carried by every alert */
enum { SM_CAM_BACKGROUND = 0, SM_CAM_FIRE = 1, SM_CAM_SMOKE = 2 };           /* camera labels */
enum { SM_FWI_ECO = 0, SM_FWI_ALERT = 1 };
enum { SM_FRAME_ALERT = 1, SM_FRAME_STATE_CHANGE = 2, SM_FRAME_HEARTBEAT = 3, SM_FRAME_LAST_GASP = 4 };
#define SM_MAX_FRAMES 4

typedef struct {
    double eco_interval_s, alert_interval_s, survival_interval_s, suspicion_interval_s;
    int flame_reads_to_trigger, clear_scans;
    double camera_confidence, camera_min_period_s;
    int alert_repeats;
    double fire_hold_clear_s, heartbeat_s;
    int pump_danger_from;               /* FWI class 'high' */
    double flame_recheck_s;             /* after a first flame read in Normal, wake again this soon (0 = off) */
} sm_config_t;

typedef struct {
    bool gas_smoke, gas_fault, flame;
    bool camera_valid;                  /* a capture finished since the previous step */
    uint8_t camera_label;               /* SM_CAM_* */
    double camera_conf;
    uint8_t fwi_mode;                   /* SM_FWI_* */
    int fwi_danger;                     /* 0..5 */
    bool battery_low, housing_hot, supply_fault;
    double dt_s;                        /* time since the previous step */
} sm_inputs_t;

typedef struct { uint8_t kind; uint8_t repeats; } sm_frame_t;

typedef struct {
    uint8_t state;
    double interval_s;                  /* sleep before the next wake-up */
    bool camera_on, gps_on, actuator;
    uint8_t reasons;                    /* SM_R_* */
    sm_frame_t frames[SM_MAX_FRAMES];
    uint8_t n_frames;
    bool last_gasp;
} sm_output_t;

typedef struct {
    sm_config_t cfg;
    uint8_t state;
    int flame_reads, clear_count;
    double fire_clear_s, since_frame_s, since_camera_s;
    bool last_gasp_sent;
    uint8_t reasons;
    bool survival;
} sm_machine_t;

void sm_config_default(sm_config_t *cfg);
/* cfg == NULL uses the defaults. */
void sm_init(sm_machine_t *m, const sm_config_t *cfg);
/* Operator or gateway acknowledgement: leave Fire. */
void sm_reset(sm_machine_t *m);
/* Zero-initialised inputs with the Python defaults (eco, dt 30 s). */
void sm_inputs_default(sm_inputs_t *x);
/* One wake-up. Returns 0, or -1 on bad arguments (NULL, dt_s negative or not finite); state untouched then. */
int sm_step(sm_machine_t *m, const sm_inputs_t *x, sm_output_t *out);

#ifdef __cplusplus
}
#endif
#endif
