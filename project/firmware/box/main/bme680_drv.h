/* BME680 through the Bosch BME68x SensorAPI: ambient reading (heater off) and the 10-step forced gas scan. */
#ifndef BME680_DRV_H
#define BME680_DRV_H
#include <stdbool.h>
#include "gas_chain.h"

bool bme_init(void);
bool bme_read_env(double *temp_c, double *rh_pct);                                       /* forced, heater off */
bool bme_scan(double gas_ohm[GC_NSTEP], double temp_c[GC_NSTEP], double rh_pct[GC_NSTEP]);
/* Heater profile: ASSUMED (the Mendeley profiles are undocumented). Ascending, so the three depth bands
 * (steps 0-2, 3-6, 7-9) are low / mid / high heater temperature. To be measured and revised on the real part. */
extern const unsigned short BME_HEATER_C[GC_NSTEP];
extern const unsigned short BME_HEATER_MS[GC_NSTEP];
#endif
