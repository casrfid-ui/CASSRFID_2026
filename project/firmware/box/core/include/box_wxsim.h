/* Simulated wind and rain of the prototype (spec 1: "simulated in the prototype and flagged in every frame").
 * Deterministic from a seed, so a run can be replayed. The gateway can override the values (dashboard test tool). */
#ifndef BOX_WXSIM_H
#define BOX_WXSIM_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    uint32_t rng;
    double wind_kmh;            /* slow random walk around a diurnal cycle */
    double rain_left_mm;        /* remaining amount of the running rain event */
    int64_t last_unix_s;
    /* override from the gateway (FFP_C_SIM_WX) */
    bool ovr;
    uint8_t ovr_wind_kmh, ovr_rain_x10;
    int64_t ovr_until_unix_s;
} box_wxsim_t;

void box_wxsim_init(box_wxsim_t *s, uint32_t seed);
void box_wxsim_override(box_wxsim_t *s, uint8_t wind_kmh, uint8_t rain_mm_h_x10, int64_t until_unix_s);
/* Advances to unix_s. Returns the wind now (km/h) and the rain fallen since the previous call (mm). */
void box_wxsim_step(box_wxsim_t *s, int64_t unix_s, double *wind_kmh, double *rain_mm);

#ifdef __cplusplus
}
#endif
#endif
