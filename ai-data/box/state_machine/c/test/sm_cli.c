/* Parity tool: one input per line: gas_smoke gas_fault flame cam_valid cam_label cam_conf fwi_alert danger
 * battery_low housing_hot supply_fault dt_s. A line "RESET" calls sm_reset.
 * Prints: state interval camera_on gps_on actuator reasons last_gasp n_frames (kind repeats)* */
#include <stdio.h>
#include <string.h>
#include "state_machine.h"

int main(void)
{
    static char line[512];
    sm_machine_t m;
    sm_init(&m, NULL);
    while (fgets(line, sizeof line, stdin)) {
        sm_inputs_t x;
        sm_output_t o;
        int v[11], i;
        double conf, dt;
        if (!strncmp(line, "RESET", 5)) { sm_reset(&m); continue; }
        if (sscanf(line, "%d %d %d %d %d %lf %d %d %d %d %d %lf", &v[0], &v[1], &v[2], &v[3], &v[4], &conf, &v[5],
                   &v[6], &v[7], &v[8], &v[9], &dt) != 12) return 3;
        sm_inputs_default(&x);
        x.gas_smoke = v[0]; x.gas_fault = v[1]; x.flame = v[2]; x.camera_valid = v[3]; x.camera_label = (uint8_t)v[4];
        x.camera_conf = conf; x.fwi_mode = (uint8_t)v[5]; x.fwi_danger = v[6]; x.battery_low = v[7];
        x.housing_hot = v[8]; x.supply_fault = v[9]; x.dt_s = dt;
        if (sm_step(&m, &x, &o) != 0) return 4;
        printf("%d %.17g %d %d %d %d %d %d", o.state, o.interval_s, o.camera_on, o.gps_on, o.actuator, o.reasons,
               o.last_gasp, o.n_frames);
        for (i = 0; i < o.n_frames; i++) printf(" %d %d", o.frames[i].kind, o.frames[i].repeats);
        printf("\n");
    }
    return 0;
}
