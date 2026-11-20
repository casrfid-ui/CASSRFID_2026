/* Everything the box application needs from the board. The ESP32 implementation is in ../main/hal_esp32.c,
 * the host tests use a scripted mock. All hooks receive `ctx`. No hook may block longer than its documented timeout. */
#ifndef BOX_HAL_H
#define BOX_HAL_H

#include <stdbool.h>
#include <stdint.h>

#include "box_camera.h"
#include "ffp.h"
#include "flame.h"
#include "gas_chain.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    void *ctx;
    int (*tx)(void *ctx, const uint8_t frame[FFP_FRAME_LEN]);                         /* 0 = sent */
    /* 1 = a frame was received (rssi in dBm, snr in 0.25 dB units), 0 = nothing before timeout_ms, < 0 = radio error */
    int (*rx)(void *ctx, uint8_t frame[FFP_FRAME_LEN], int *rssi_dbm, int *snr_x4, uint32_t timeout_ms);
    int (*set_sf)(void *ctx, int sf);                                                  /* 7..12 */
} box_radio_t;

typedef struct {
    void *ctx;
    uint32_t (*now_ms)(void *ctx);                      /* since this wake-up started; only differences are used */
    void (*delay_ms)(void *ctx, uint32_t ms);
    int64_t (*rtc_unix_s)(void *ctx);                   /* system clock, UTC; keeps counting in deep sleep */
    void (*rtc_set_unix_s)(void *ctx, int64_t unix_s);
    uint32_t (*random32)(void *ctx);

    bool (*read_env)(void *ctx, double *temp_c, double *rh_pct);                      /* ambient T / RH, heater off */
    void (*gas_power)(void *ctx, bool on);
    bool (*scan_gas)(void *ctx, double gas_ohm[GC_NSTEP], double temp_c[GC_NSTEP], double rh_pct[GC_NSTEP]);
    void (*flame_burst)(void *ctx, uint8_t raw[FL_MAX_SAMPLES], int n);               /* n reads of the KY-026 output */

    int (*battery_pct)(void *ctx);                      /* 0..100 */
    bool (*battery_low)(void *ctx);
    bool (*housing_hot)(void *ctx);
    bool (*supply_fault)(void *ctx);

    void (*gps_power)(void *ctx, bool on);
    /* Reads NMEA for up to timeout_ms. true when a valid fix was obtained (pos, and the UTC time when known else -1). */
    bool (*gps_poll)(void *ctx, ffp_pos_t *pos, int64_t *unix_s, uint32_t timeout_ms);
    void (*pump)(void *ctx, bool on);

    const cam_hw_t *(*camera_hw)(void *ctx);            /* NULL = no camera on this build */
    void (*sleep_s)(void *ctx, double seconds);         /* deep sleep with timer + flame pin wake; on the host: returns */

    box_radio_t radio;
} box_hal_t;

#ifdef __cplusplus
}
#endif
#endif
