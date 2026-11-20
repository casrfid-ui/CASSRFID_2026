#include "hdlc.h"

#include <string.h>

uint16_t hdlc_crc16(const uint8_t *d, size_t n)
{
    uint16_t c = 0xFFFF;
    size_t i;
    int k;
    for (i = 0; i < n; i++) {
        c ^= (uint16_t)((uint16_t)d[i] << 8);
        for (k = 0; k < 8; k++) c = (uint16_t)((c & 0x8000) ? ((c << 1) ^ 0x1021) : (c << 1));
    }
    return c;
}

static int put(uint8_t *out, size_t cap, size_t *n, uint8_t b)
{
    if (b == 0x7E || b == 0x7D) {
        if (*n + 2 > cap) return -1;
        out[(*n)++] = 0x7D; out[(*n)++] = (uint8_t)(b ^ 0x20);
    } else {
        if (*n + 1 > cap) return -1;
        out[(*n)++] = b;
    }
    return 0;
}

int hdlc_encode(uint8_t type, const uint8_t *p, size_t len, uint8_t *out, size_t cap)
{
    uint8_t raw[HDLC_MAX_PAYLOAD + 1];
    uint16_t crc;
    size_t i, n = 0;
    if (len > HDLC_MAX_PAYLOAD || cap < 2) return -1;
    raw[0] = type;
    if (len) memcpy(raw + 1, p, len);
    crc = hdlc_crc16(raw, len + 1);
    out[n++] = 0x7E;
    for (i = 0; i < len + 1; i++) if (put(out, cap, &n, raw[i])) return -1;
    if (put(out, cap, &n, (uint8_t)(crc >> 8)) || put(out, cap, &n, (uint8_t)crc)) return -1;
    if (n + 1 > cap) return -1;
    out[n++] = 0x7E;
    return (int)n;
}

void hdlc_decoder_init(hdlc_decoder_t *d) { memset(d, 0, sizeof *d); }

int hdlc_feed(hdlc_decoder_t *d, uint8_t b, hdlc_msg_t *m)
{
    if (b == 0x7E) {
        int ok = 0;
        if (d->in_frame && d->n >= 3) {
            uint16_t crc = hdlc_crc16(d->buf, d->n - 2), got = (uint16_t)((d->buf[d->n - 2] << 8) | d->buf[d->n - 1]);
            if (crc == got) {
                m->type = d->buf[0];
                m->len = (uint8_t)(d->n - 3);
                memcpy(m->data, d->buf + 1, m->len);
                ok = 1;
            } else d->bad_crc++;
        }
        d->n = 0; d->in_frame = 1; d->escape = 0;
        return ok;
    }
    if (!d->in_frame) return 0;
    if (b == 0x7D) { d->escape = 1; return 0; }
    if (d->escape) { b ^= 0x20; d->escape = 0; }
    if (d->n >= sizeof d->buf) { d->overflow++; d->in_frame = 0; d->n = 0; return 0; }
    d->buf[d->n++] = b;
    return 0;
}
