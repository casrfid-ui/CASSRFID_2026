/* Wake-up loop of the box. NOT compiled or run in this repository: skeleton to be built with the firmware once the
 * board drivers (board.h) exist. The logic itself is in box_runtime.c, which is tested on the host. */
#include "board.h"
#include "box_nvs.h"
#include "nvs_flash.h"

static box_runtime_t rt;
static cam_workspace_t cam_ws;                                 /* ~20 kB: static, not on the stack */
static uint8_t cam_jpeg[60 * 1024];
static uint32_t cam_req_id;
static uint8_t cam_last_status;                                /* CAM_*: report it to the dashboard (sensor fault if quality/power) */
static bool pending_camera;
static uint8_t pending_label;
static double pending_conf;

void app_main(void)
{
    box_config_t cfg;
    nvs_flash_init();
    box_config_default(&cfg);
    cfg.utc_offset_s = 0;                                      /* set to the site's offset */
    if (box_runtime_init(&rt, &cfg, &box_nvs_kv) < 0) for (;;) board_sleep(3600.0);   /* bad config: nothing safe to do */

    for (;;) {
        box_tick_t t = {0};
        box_output_t o;

        t.unix_s = board_unix_s();
        t.weather_valid = board_read_weather(&t.temp_c, &t.rh_pct, &t.wind_kmh);
        t.rain_mm = board_take_rain_mm();
        t.battery_low = board_battery_low();
        t.housing_hot = board_housing_hot();
        t.supply_fault = board_supply_fault();
        board_flame_burst(t.flame_raw, cfg.flame.burst_samples);
        t.flame_n = (uint8_t)cfg.flame.burst_samples;
        if (!t.battery_low) {                                  /* Survival: the gas sensor stays off */
            board_gas_power(true);
            t.gas_valid = board_scan_gas(t.gas_ohm, t.gas_temp_c, t.gas_rh_pct);
            board_gas_power(false);
        }
        if (pending_camera) {                                  /* capture started at the previous wake-up */
            t.camera_valid = true; t.camera_label = pending_label; t.camera_conf = pending_conf;
            pending_camera = false;
        }

        if (box_runtime_step(&rt, &t, &o) == 0) {
            board_gps_power(o.sm.gps_on);
            board_pump(o.sm.actuator);
            if (o.sm.camera_on) {                              /* only after an alert: capture, send, gateway CNN answers */
                cam_config_t cc; cam_ids_t ids; cam_result_t cr;
                cam_config_default(&cc);
                ids.box_id = BOX_ID; ids.req_id = ++cam_req_id; ids.unix_s = t.unix_s; ids.reasons = o.sm.reasons;
                cam_session_run(board_camera_hw(), &cc, &ids, &cam_ws, cam_jpeg, sizeof cam_jpeg, &cr);
                cam_last_status = cr.status;
                if (cr.valid) { pending_label = cr.label; pending_conf = cr.conf; pending_camera = true; }
            }
            if (o.sm.n_frames > 0) board_send_frames(&o);
            board_sleep(o.sm.interval_s);
        } else {
            board_sleep(300.0);                                /* bad arguments (RTC not set?): retry later */
        }
    }
}
