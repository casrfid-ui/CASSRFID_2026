/* box_sim SCENARIO BOX_ID [WAKES] [noack]
 * Runs the real box application (same C as the firmware) against a scripted board and prints every transmitted frame:
 *   "<unix_s> <box_id> <hex32>"
 * Scenarios: quiet (clean air), fire (clean air, then smoke and flame), smoke (gas only), fault (supply fault).
 * Used by the gateway integration tests. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "box_app.h"
#include "mock_hal.h"

static mock_t mk;
static box_retained_t ret;
static box_app_t app;

int main(int argc, char **argv)
{
    const char *sc = argc > 1 ? argv[1] : "quiet";
    int id = argc > 2 ? atoi(argv[2]) : 1, wakes = argc > 3 ? atoi(argv[3]) : 100, i, printed = 0;
    bool noack = argc > 4 && strcmp(argv[4], "noack") == 0;
    box_app_cfg_t c;

    mock_init(&mk);
    mk.gw_dead = noack;
    mk.gps_has_fix = true; mk.gps_pos.lat_e7 = 365000000 + id * 2000; mk.gps_pos.lon_e7 = 100000000 + id * 3000; mk.gps_pos.alt_m = 120; mk.gps_pos.sats = 8;
    mk.gps_unix = mk.base_unix;
    box_app_cfg_default(&c, (uint8_t)id, (uint8_t)(id == 1 ? 2 : 1));
    c.gps_boot_timeout_ms = 1000;
    if (box_app_init(&app, &c, &mk.hal, &ret, NULL) != 0) return 2;

    for (i = 0; i < wakes; i++) {
        double s;
        if (strcmp(sc, "fire") == 0 && i >= 40) { mk.gas_scale = 0.25; mk.flame_on = true; mk.cam_answer_label = "fire"; mk.cam_answer_conf = 0.9; }
        if (strcmp(sc, "smoke") == 0 && i >= 40) mk.gas_scale = 0.25;
        if (strcmp(sc, "fault") == 0 && i >= 20) mk.supply_fault = true;
        s = box_app_wake(&app);
        for (; printed < mk.n_tx && printed < MOCK_TXLOG; printed++) {
            int k;
            printf("%lld %d ", (long long)(mk.base_unix + ret.link.seq * 0 + (int64_t)(mk.tx_ms[printed] / 1000)), id);
            for (k = 0; k < FFP_FRAME_LEN; k++) printf("%02x", mk.tx_log[printed][k]);
            printf("\n");
        }
        mk.ms += (uint32_t)(s * 1000.0);
        if (mk.n_tx >= MOCK_TXLOG - 8) { mk.n_tx = 0; printed = 0; }
    }
    return 0;
}
