/* Parity tool.
 *   "Q w h min_mean min_std max_sat min_grad v0 v1 ..."  -> mean std sat_frac dark_frac grad flags      (17 digits)
 *   "P expect_id <json body>"                              -> rc label conf model_ms
 *   "H box_id req_id unix_s reasons"                       -> the headers, then a line "END"            */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "box_camera.h"

int main(void)
{
    static char line[200000];
    static uint8_t luma[CAM_LUMA_MAX];
    while (fgets(line, sizeof line, stdin)) {
        char *p = line + 1, *e;
        if (line[0] == 'Q') {
            cam_config_t c;
            cam_quality_t q;
            int w = (int)strtol(p, &e, 10), h, i;
            p = e; h = (int)strtol(p, &e, 10); p = e;
            cam_config_default(&c);
            c.min_mean = strtod(p, &e); p = e;
            c.min_std = strtod(p, &e); p = e;
            c.max_sat_frac = strtod(p, &e); p = e;
            c.min_grad = strtod(p, &e); p = e;
            for (i = 0; i < w * h && i < CAM_LUMA_MAX; i++) { luma[i] = (uint8_t)strtol(p, &e, 10); p = e; }
            if (cam_quality(luma, w, h, &c, &q) != 0) { printf("ERR\n"); continue; }
            printf("%.17g %.17g %.17g %.17g %.17g %d\n", q.mean, q.std, q.sat_frac, q.dark_frac, q.grad, q.flags);
        } else if (line[0] == 'P') {
            unsigned long id = strtoul(p, &e, 10);
            uint8_t label = 0; double conf = 0; int ms = 0, rc;
            p = e;
            while (*p == ' ') p++;
            line[strcspn(line, "\r\n")] = '\0';
            rc = cam_parse_response(p, (uint32_t)id, &label, &conf, &ms);
            printf("%d %d %.17g %d\n", rc, rc == 0 ? label : -1, rc == 0 ? conf : 0.0, rc == 0 ? ms : -1);
        } else if (line[0] == 'H') {
            cam_ids_t ids; char buf[CAM_HEADERS_MAX];
            ids.box_id = (uint8_t)strtoul(p, &e, 10); p = e;
            ids.req_id = (uint32_t)strtoul(p, &e, 10); p = e;
            ids.unix_s = strtoll(p, &e, 10); p = e;
            ids.reasons = (uint8_t)strtoul(p, &e, 10);
            if (cam_build_headers(buf, sizeof buf, &ids) < 0) printf("ERR\n"); else printf("%sEND\n", buf);
        }
    }
    return 0;
}
