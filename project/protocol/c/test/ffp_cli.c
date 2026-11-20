/* ffp_cli decode HEX32  -> one line "key=value ..." for the Python mirror test. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "ffp.h"

int main(int argc, char **argv)
{
    uint8_t b[FFP_FRAME_LEN];
    ffp_frame_t f;
    int i, r;
    if (argc != 3 || strcmp(argv[1], "decode") != 0 || strlen(argv[2]) != 32) return 2;
    for (i = 0; i < 16; i++) { unsigned v; sscanf(argv[2] + 2 * i, "%2x", &v); b[i] = (uint8_t)v; }
    r = ffp_decode(b, 16, &f);
    if (r) { printf("error=%d\n", r); return 0; }
    printf("type=%d flags=%d origin=%d dest=%d seq=%d", f.type, f.flags, f.origin, f.dest, f.seq);
    if (f.type <= 4) {
        ffp_status_t s; ffp_unpack_status(&f, &s);
        printf(" state=%d mode=%d reasons=%d gas_score=%d gas_class=%d gas_faults=%d warmup=%d flame=%d scan_bad=%d cam_label=%d cam_valid=%d cam_status=%d cam_conf=%d sflags=%d fwi_x2=%d danger=%d fwi_updated=%d provisional=%d repeat=%d battery_pct=%d b0=%d b1=%d b2=%d",
               s.state, s.mode, s.reasons, s.gas_score, s.gas_class, s.gas_faults, s.warmup, s.flame, s.scan_bad, s.cam_label, s.cam_valid, s.cam_status,
               s.cam_conf, s.flags, s.fwi_x2, s.danger, s.fwi_updated, s.provisional, s.repeat, s.battery_pct, s.band[0], s.band[1], s.band[2]);
    }
    printf("\n");
    return 0;
}
