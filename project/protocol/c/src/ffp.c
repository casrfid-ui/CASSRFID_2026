#include "ffp.h"

#include <math.h>
#include <string.h>

uint8_t ffp_crc8(const uint8_t *d, size_t n)
{
    uint8_t c = 0;
    size_t i;
    int k;
    for (i = 0; i < n; i++) {
        c ^= d[i];
        for (k = 0; k < 8; k++) c = (uint8_t)((c & 0x80) ? ((c << 1) ^ 0x07) : (c << 1));
    }
    return c;
}

uint8_t ffp_q8(double x, double scale)
{
    double v;
    if (x != x) return 0;
    v = floor(x * scale + 0.5);
    return v <= 0 ? 0 : v >= 255 ? 255 : (uint8_t)v;
}

uint16_t ffp_q16(double x, double scale)
{
    double v;
    if (x != x) return 0;
    v = floor(x * scale + 0.5);
    return v <= 0 ? 0 : v >= 65535 ? 65535 : (uint16_t)v;
}

static int known_type(uint8_t t)
{
    return (t >= FFP_T_ALERT && t <= FFP_T_POS) || (t >= FFP_T_ACK && t <= FFP_T_TIME);
}

static int is_box_type(uint8_t t) { return t >= FFP_T_ALERT && t <= FFP_T_POS; }

void ffp_frame_init(ffp_frame_t *f, uint8_t type, uint8_t flags, uint8_t origin, uint8_t dest, uint8_t seq)
{
    memset(f, 0, sizeof *f);
    f->type = type; f->flags = (uint8_t)(flags & 0x0F); f->origin = (uint8_t)(origin & 0x0F);
    f->dest = (uint8_t)(dest & 0x0F); f->seq = seq;
}

int ffp_encode(const ffp_frame_t *f, uint8_t out[FFP_FRAME_LEN])
{
    if (!f || !out) return -1;
    if (!known_type(f->type) || f->flags > 0x0F || f->origin > 15 || f->dest > 15) return -1;
    out[0] = (uint8_t)((f->type << 4) | f->flags);
    out[1] = (uint8_t)((f->origin << 4) | f->dest);
    out[2] = f->seq;
    memcpy(out + 3, f->payload, FFP_PAYLOAD_LEN);
    out[15] = ffp_crc8(out, 15);
    return 0;
}

int ffp_decode(const uint8_t *in, size_t len, ffp_frame_t *f)
{
    uint8_t type;
    if (!in || !f || len != FFP_FRAME_LEN) return -1;
    if (ffp_crc8(in, 15) != in[15]) return -2;
    type = (uint8_t)(in[0] >> 4);
    if (!known_type(type)) return -3;
    f->type = type; f->flags = (uint8_t)(in[0] & 0x0F);
    f->origin = (uint8_t)(in[1] >> 4); f->dest = (uint8_t)(in[1] & 0x0F); f->seq = in[2];
    memcpy(f->payload, in + 3, FFP_PAYLOAD_LEN);
    if (is_box_type(type) ? (f->origin < FFP_ID_BOX_MIN || f->origin > FFP_ID_BOX_MAX)
                          : (f->origin < FFP_ID_GW_MIN || f->origin > FFP_ID_GW_MAX))
        return -4;
    return 0;
}

void ffp_pack_status(ffp_frame_t *f, const ffp_status_t *s)
{
    uint8_t *p = f->payload;
    p[0] = (uint8_t)((s->state & 3) | ((s->mode & 3) << 2) | ((s->reasons & 15) << 4));
    p[1] = s->gas_score;
    p[2] = (uint8_t)((s->gas_class & 3) | ((s->gas_faults & 7) << 2) | ((s->warmup & 1) << 5) | ((s->flame & 1) << 6) | ((s->scan_bad & 1) << 7));
    p[3] = (uint8_t)((s->cam_label & 3) | ((s->cam_valid & 1) << 2) | ((s->cam_status & 15) << 3));
    p[4] = s->cam_conf;
    p[5] = s->flags;
    p[6] = s->fwi_x2;
    p[7] = (uint8_t)((s->danger & 7) | ((s->fwi_updated & 1) << 3) | ((s->provisional & 1) << 4) | ((s->repeat & 3) << 5));
    p[8] = s->battery_pct;
    p[9] = s->band[0]; p[10] = s->band[1]; p[11] = s->band[2];
}

void ffp_unpack_status(const ffp_frame_t *f, ffp_status_t *s)
{
    const uint8_t *p = f->payload;
    s->state = p[0] & 3; s->mode = (p[0] >> 2) & 3; s->reasons = (p[0] >> 4) & 15;
    s->gas_score = p[1];
    s->gas_class = p[2] & 3; s->gas_faults = (p[2] >> 2) & 7; s->warmup = (p[2] >> 5) & 1; s->flame = (p[2] >> 6) & 1; s->scan_bad = (p[2] >> 7) & 1;
    s->cam_label = p[3] & 3; s->cam_valid = (p[3] >> 2) & 1; s->cam_status = (p[3] >> 3) & 15;
    s->cam_conf = p[4];
    s->flags = p[5];
    s->fwi_x2 = p[6];
    s->danger = p[7] & 7; s->fwi_updated = (p[7] >> 3) & 1; s->provisional = (p[7] >> 4) & 1; s->repeat = (p[7] >> 5) & 3;
    s->battery_pct = p[8];
    s->band[0] = p[9]; s->band[1] = p[10]; s->band[2] = p[11];
}

void ffp_pack_telem(ffp_frame_t *f, const ffp_telem_t *t)
{
    uint8_t *p = f->payload;
    uint16_t u = (uint16_t)t->temp_c100;
    p[0] = (uint8_t)(u >> 8); p[1] = (uint8_t)u;
    p[2] = t->rh_x2; p[3] = t->wind_kmh; p[4] = t->rain_x10; p[5] = t->ffmc_x2_5; p[6] = t->dmc;
    p[7] = (uint8_t)(t->dc >> 8); p[8] = (uint8_t)t->dc;
    p[9] = t->isi_x5; p[10] = t->bui;
    p[11] = (uint8_t)((t->history_hours & 31) | ((t->provisional & 1) << 5));
}

void ffp_unpack_telem(const ffp_frame_t *f, ffp_telem_t *t)
{
    const uint8_t *p = f->payload;
    t->temp_c100 = (int16_t)(uint16_t)((p[0] << 8) | p[1]);
    t->rh_x2 = p[2]; t->wind_kmh = p[3]; t->rain_x10 = p[4]; t->ffmc_x2_5 = p[5]; t->dmc = p[6];
    t->dc = (uint16_t)((p[7] << 8) | p[8]);
    t->isi_x5 = p[9]; t->bui = p[10];
    t->history_hours = p[11] & 31; t->provisional = (p[11] >> 5) & 1;
}

static void put32(uint8_t *p, uint32_t v) { p[0] = (uint8_t)(v >> 24); p[1] = (uint8_t)(v >> 16); p[2] = (uint8_t)(v >> 8); p[3] = (uint8_t)v; }
static uint32_t get32(const uint8_t *p) { return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | p[3]; }

void ffp_pack_pos(ffp_frame_t *f, const ffp_pos_t *q)
{
    uint8_t *p = f->payload;
    put32(p, (uint32_t)q->lat_e7); put32(p + 4, (uint32_t)q->lon_e7);
    p[8] = (uint8_t)((uint16_t)q->alt_m >> 8); p[9] = (uint8_t)q->alt_m; p[10] = q->sats; p[11] = q->fix;
}

void ffp_unpack_pos(const ffp_frame_t *f, ffp_pos_t *q)
{
    const uint8_t *p = f->payload;
    q->lat_e7 = (int32_t)get32(p); q->lon_e7 = (int32_t)get32(p + 4);
    q->alt_m = (int16_t)(uint16_t)((p[8] << 8) | p[9]); q->sats = p[10]; q->fix = p[11];
}

void ffp_pack_ack(ffp_frame_t *f, const ffp_ack_t *a)
{
    uint8_t *p = f->payload;
    p[0] = a->acked_seq; p[1] = a->acked_type; p[2] = a->flags; p[3] = (uint8_t)a->rssi_dbm; p[4] = (uint8_t)a->snr_x4;
    p[5] = a->gw_id; p[6] = a->alert_level;
}

void ffp_unpack_ack(const ffp_frame_t *f, ffp_ack_t *a)
{
    const uint8_t *p = f->payload;
    a->acked_seq = p[0]; a->acked_type = p[1]; a->flags = p[2]; a->rssi_dbm = (int8_t)p[3]; a->snr_x4 = (int8_t)p[4];
    a->gw_id = p[5]; a->alert_level = p[6];
}

void ffp_pack_cmd(ffp_frame_t *f, const ffp_cmd_t *c)
{
    f->payload[0] = c->id;
    memcpy(f->payload + 1, c->arg, 6);
}

void ffp_unpack_cmd(const ffp_frame_t *f, ffp_cmd_t *c)
{
    c->id = f->payload[0];
    memcpy(c->arg, f->payload + 1, 6);
}

void ffp_pack_time(ffp_frame_t *f, const ffp_time_t *t)
{
    put32(f->payload, t->unix_s);
    f->payload[4] = (uint8_t)t->utc_offset_q;
}

void ffp_unpack_time(const ffp_frame_t *f, ffp_time_t *t)
{
    t->unix_s = get32(f->payload);
    t->utc_offset_q = (int8_t)f->payload[4];
}
