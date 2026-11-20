/* What the firmware (iot) must provide to the runtime. Declarations only: the drivers are not written here.
 * Every function is called once per wake-up from main.c. */
#ifndef BOARD_H
#define BOARD_H
#include <stdbool.h>
#include <stdint.h>
#include "box_runtime.h"
#include "box_camera.h"

#ifndef BOX_ID
#define BOX_ID 1                                               /* set per box at build time */
#endif

int64_t board_unix_s(void);                                   /* RTC, UTC seconds; must be set (NTP/GPS/gateway) */
bool    board_read_weather(double *temp_c, double *rh_pct, double *wind_kmh);   /* wind simulated in the prototype */
double  board_take_rain_mm(void);                             /* rain since the previous call (simulated in the prototype) */
/* BME680, forced mode: GC_NSTEP forced measurements, one heater temperature each (profile to define, see FICHE). */
bool    board_scan_gas(double gas_ohm[GC_NSTEP], double temp_c[GC_NSTEP], double rh_pct[GC_NSTEP]);
/* KY-026 digital output: `n` reads at a fixed spacing (e.g. 8 reads, 10 ms apart); fills raw[] with 0 / 1 */
void    board_flame_burst(uint8_t raw[FL_MAX_SAMPLES], int n);
/* Camera session hooks (OV2640 driver, Wi-Fi client, HTTP POST to the gateway): see box/camera/FICHE.md.
 * The CNN runs on the gateway; the box only captures and sends. */
const cam_hw_t *board_camera_hw(void);
bool    board_battery_low(void);
bool    board_housing_hot(void);
bool    board_supply_fault(void);

void    board_gps_power(bool on);
void    board_pump(bool on);
void    board_gas_power(bool on);
void    board_send_frames(const box_output_t *out);          /* builds and sends the LoRa frames listed in out->sm.frames */
void    board_sleep(double seconds);                          /* timer wake-up; the flame pin is also a wake source */
#endif
