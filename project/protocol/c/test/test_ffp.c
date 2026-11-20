/* Host tests of the frame codec + a vector dump read by the Python mirror test. */
#include <stdio.h>
#include <string.h>

#include "ffp.h"

static int fails, checks;
#define CHECK(c) do { checks++; if (!(c)) { fails++; printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #c); } } while (0)

static void hex(const uint8_t *b, FILE *o) { int i; for (i = 0; i < FFP_FRAME_LEN; i++) fprintf(o, "%02x", b[i]); }

static ffp_status_t sample_status(unsigned seed)
{
    ffp_status_t s;
    memset(&s, 0, sizeof s);
    s.state = seed % 3; s.mode = seed % 3; s.reasons = (seed * 7) & 15; s.gas_score = (uint8_t)(seed * 37);
    s.gas_class = seed & 3; s.gas_faults = (seed >> 1) & 7; s.warmup = seed & 1; s.flame = (seed >> 2) & 1; s.scan_bad = (seed >> 3) & 1;
    s.cam_label = seed % 3; s.cam_valid = seed & 1; s.cam_status = seed % 9; s.cam_conf = (uint8_t)(seed * 91);
    s.flags = (uint8_t)(seed * 53); s.fwi_x2 = (uint8_t)(seed * 29); s.danger = seed % 6; s.fwi_updated = seed & 1;
    s.provisional = (seed >> 1) & 1; s.repeat = seed & 3; s.battery_pct = (uint8_t)(seed * 13 % 101);
    s.band[0] = (uint8_t)(seed * 3); s.band[1] = (uint8_t)(seed * 5); s.band[2] = (uint8_t)(seed * 11);
    return s;
}

int main(int argc, char **argv)
{
    uint8_t w[FFP_FRAME_LEN];
    ffp_frame_t f, g;
    ffp_status_t s, s2;
    ffp_telem_t t, t2;
    ffp_pos_t p, p2;
    ffp_ack_t a, a2;
    ffp_cmd_t c, c2;
    ffp_time_t tm, tm2;
    unsigned i;
    FILE *vec = argc > 1 ? fopen(argv[1], "w") : NULL;

    /* CRC-8/SMBUS check value of "123456789" is 0xF4 */
    CHECK(ffp_crc8((const uint8_t *)"123456789", 9) == 0xF4);

    for (i = 0; i < 40; i++) {
        s = sample_status(i);
        ffp_frame_init(&f, (uint8_t)(1 + i % 4), (uint8_t)(i & 15), (uint8_t)(1 + i % 7), (uint8_t)(i % 3 ? 0 : 15), (uint8_t)(i * 5));
        ffp_pack_status(&f, &s);
        CHECK(ffp_encode(&f, w) == 0);
        CHECK(ffp_decode(w, FFP_FRAME_LEN, &g) == 0);
        CHECK(g.type == f.type && g.flags == f.flags && g.origin == f.origin && g.dest == f.dest && g.seq == f.seq);
        ffp_unpack_status(&g, &s2);
        CHECK(memcmp(&s, &s2, sizeof s) == 0);
        if (vec) { fprintf(vec, "status "); hex(w, vec); fprintf(vec, "\n"); }
    }

    memset(&t, 0, sizeof t);
    t.temp_c100 = -1234; t.rh_x2 = 99; t.wind_kmh = 31; t.rain_x10 = 7; t.ffmc_x2_5 = 212; t.dmc = 41; t.dc = 513; t.isi_x5 = 66; t.bui = 77;
    t.history_hours = 24; t.provisional = 1;
    ffp_frame_init(&f, FFP_T_TELEM, FFP_F_SIM_WX, 2, 0, 9);
    ffp_pack_telem(&f, &t); CHECK(ffp_encode(&f, w) == 0); CHECK(ffp_decode(w, 16, &g) == 0);
    ffp_unpack_telem(&g, &t2); CHECK(memcmp(&t, &t2, sizeof t) == 0);
    if (vec) { fprintf(vec, "telem "); hex(w, vec); fprintf(vec, "\n"); }

    p.lat_e7 = 365000123; p.lon_e7 = -98000456; p.alt_m = -12; p.sats = 7; p.fix = 1;
    ffp_frame_init(&f, FFP_T_POS, 0, 1, 0, 200);
    ffp_pack_pos(&f, &p); CHECK(ffp_encode(&f, w) == 0); CHECK(ffp_decode(w, 16, &g) == 0);
    ffp_unpack_pos(&g, &p2); CHECK(memcmp(&p, &p2, sizeof p) == 0);
    if (vec) { fprintf(vec, "pos "); hex(w, vec); fprintf(vec, "\n"); }

    a.acked_seq = 77; a.acked_type = FFP_T_ALERT; a.flags = FFP_AF_OPERATOR | FFP_AF_SBC_UP; a.rssi_dbm = -97; a.snr_x4 = -22; a.gw_id = 8; a.alert_level = 3;
    ffp_frame_init(&f, FFP_T_ACK, 0, 8, 1, 3);
    ffp_pack_ack(&f, &a); CHECK(ffp_encode(&f, w) == 0); CHECK(ffp_decode(w, 16, &g) == 0);
    ffp_unpack_ack(&g, &a2); CHECK(memcmp(&a, &a2, sizeof a) == 0);
    if (vec) { fprintf(vec, "ack "); hex(w, vec); fprintf(vec, "\n"); }

    c.id = FFP_C_SET_THRESH; for (i = 0; i < 6; i++) c.arg[i] = (uint8_t)(10 * i + 1);
    ffp_frame_init(&f, FFP_T_CMD, 0, 8, 2, 4);
    ffp_pack_cmd(&f, &c); CHECK(ffp_encode(&f, w) == 0); CHECK(ffp_decode(w, 16, &g) == 0);
    ffp_unpack_cmd(&g, &c2); CHECK(memcmp(&c, &c2, sizeof c) == 0);
    if (vec) { fprintf(vec, "cmd "); hex(w, vec); fprintf(vec, "\n"); }

    tm.unix_s = 1794000000u; tm.utc_offset_q = 4;
    ffp_frame_init(&f, FFP_T_TIME, 0, 8, 15, 5);
    ffp_pack_time(&f, &tm); CHECK(ffp_encode(&f, w) == 0); CHECK(ffp_decode(w, 16, &g) == 0);
    ffp_unpack_time(&g, &tm2); CHECK(tm.unix_s == tm2.unix_s && tm.utc_offset_q == tm2.utc_offset_q);
    if (vec) { fprintf(vec, "time "); hex(w, vec); fprintf(vec, "\n"); }

    /* rejections */
    ffp_frame_init(&f, FFP_T_ALERT, 0, 1, 0, 1); ffp_encode(&f, w);
    CHECK(ffp_decode(w, 15, &g) == -1);
    w[5] ^= 0x10; CHECK(ffp_decode(w, 16, &g) == -2); w[5] ^= 0x10;
    w[0] = (uint8_t)((7 << 4) | 0); w[15] = ffp_crc8(w, 15); CHECK(ffp_decode(w, 16, &g) == -3);
    ffp_frame_init(&f, FFP_T_ALERT, 0, 9, 0, 1); ffp_encode(&f, w); CHECK(ffp_decode(w, 16, &g) == -4);   /* a box frame from a gateway id */
    ffp_frame_init(&f, FFP_T_ACK, 0, 2, 1, 1); ffp_encode(&f, w); CHECK(ffp_decode(w, 16, &g) == -4);     /* an ack from a box id */
    f.type = 6 + 8 + 0; CHECK(ffp_encode(&f, w) == -1);                                                    /* type 14 unknown */
    CHECK(ffp_encode(NULL, w) == -1);

    /* saturating helpers */
    CHECK(ffp_q8(-3, 255) == 0); CHECK(ffp_q8(2, 255) == 255); CHECK(ffp_q8(0.5, 255) == 128); CHECK(ffp_q8((0.0 / (double)(argc - argc)), 1) == 0);
    CHECK(ffp_q16(70000, 1) == 65535);

    if (vec) fclose(vec);
    printf("%d checks, %d failed\n", checks, fails);
    return fails ? 1 : 0;
}
