#include "box_link.h"

#include <string.h>

void box_link_cfg_default(box_link_cfg_t *c)
{
    c->alert_gap_ms = 1200;
    c->ack_wait_ms = 1500;
    c->relay_wait_ms = 1500;
    c->gw_ok_window_s = 1800;
    c->routine_tries = 2;
    c->max_flush = 6;
}

void box_link_state_init(box_link_state_t *s)
{
    memset(s, 0, sizeof *s);
}

void box_link_init(box_link_t *l, const box_link_cfg_t *cfg, box_link_state_t *st, const box_hal_t *hal, uint8_t my_id, uint8_t other_id)
{
    l->cfg = *cfg; l->st = st; l->hal = hal; l->my_id = my_id; l->other_id = other_id;
}

bool box_link_gateway_reachable(const box_link_t *l, int64_t now_unix)
{
    return l->st->last_gw_ack_unix > 0 && now_unix - l->st->last_gw_ack_unix <= (int64_t)l->cfg.gw_ok_window_s;
}

static bool seen_before(box_link_state_t *s, uint8_t origin, uint8_t seq, uint8_t type)
{
    int i;
    for (i = 0; i < BOX_SEEN_N; i++)
        if (s->seen[i][0] == origin && s->seen[i][1] == seq && s->seen[i][2] == type) return true;
    return false;
}

static void remember(box_link_state_t *s, uint8_t origin, uint8_t seq, uint8_t type)
{
    s->seen[s->seen_pos][0] = origin; s->seen[s->seen_pos][1] = seq; s->seen[s->seen_pos][2] = type;
    s->seen_pos = (uint8_t)((s->seen_pos + 1) % BOX_SEEN_N);
}

static void dl_add(box_downlinks_t *dl, const box_downlink_t *d)
{
    if (dl && dl->n < BOX_DL_MAX) dl->items[dl->n++] = *d;
}

static int send_frame(box_link_t *l, const ffp_frame_t *f)
{
    uint8_t w[FFP_FRAME_LEN];
    if (ffp_encode(f, w) != 0) return -1;
    l->st->tx_count++;
    return l->hal->radio.tx(l->hal->radio.ctx, w);
}

static int send_raw(box_link_t *l, const uint8_t w[FFP_FRAME_LEN])
{
    l->st->tx_count++;
    return l->hal->radio.tx(l->hal->radio.ctx, w);
}

/* Receives one frame within timeout_ms and handles it. Returns 1 if the frame was an ack for (my_id, seq, type) when seq >= 0. */
static int rx_once(box_link_t *l, uint32_t timeout_ms, box_downlinks_t *dl, int64_t now_unix, int want_seq, int want_type, int relay)
{
    uint8_t w[FFP_FRAME_LEN];
    ffp_frame_t f;
    int rssi = 0, snr = 0, r, got = 0;
    r = l->hal->radio.rx(l->hal->radio.ctx, w, &rssi, &snr, timeout_ms);
    if (r <= 0) return 0;
    l->st->rx_count++;
    r = ffp_decode(w, FFP_FRAME_LEN, &f);
    if (r != 0) { l->st->crc_errors++; return 0; }
    if (f.type == FFP_T_ACK || f.type == FFP_T_CMD || f.type == FFP_T_TIME) {
        box_downlink_t d;
        if (f.dest != l->my_id && f.dest != FFP_ID_BROADCAST) {
            /* an ack for somebody else proves a gateway is alive, and cancels a pending relay of that frame */
            if (f.type == FFP_T_ACK) {
                ffp_ack_t a; ffp_unpack_ack(&f, &a);
                if (relay && want_seq >= 0 && f.dest == l->other_id && a.acked_seq == (uint8_t)want_seq) got = 1;
            }
            return got;
        }
        if (seen_before(l->st, f.origin, f.seq, f.type) && f.type != FFP_T_ACK) return 0;   /* repeated command */
        if (f.type != FFP_T_ACK) remember(l->st, f.origin, f.seq, f.type);
        memset(&d, 0, sizeof d);
        d.kind = f.type; d.rssi_dbm = rssi; d.snr_x4 = snr;
        if (f.type == FFP_T_ACK) {
            ffp_unpack_ack(&f, &d.ack);
            l->st->last_gw_ack_unix = now_unix > 0 ? now_unix : 1;
            if (want_seq >= 0 && !relay && d.ack.acked_seq == (uint8_t)want_seq && d.ack.acked_type == (uint8_t)want_type) got = 1;
        } else if (f.type == FFP_T_CMD) ffp_unpack_cmd(&f, &d.cmd);
        else ffp_unpack_time(&f, &d.time);
        dl_add(dl, &d);
        return got;
    }
    /* a frame of the other box */
    if (relay == 0 && l->other_id && f.origin == l->other_id && !(f.flags & FFP_F_RELAYED) && f.dest == FFP_ID_ANY_GW) {
        if (!seen_before(l->st, f.origin, f.seq, f.type)) {
            remember(l->st, f.origin, f.seq, f.type);
            /* wait for a gateway ack of that frame; relay only if none comes */
            {
                uint32_t t0 = l->hal->now_ms(l->hal->ctx), waited = 0;
                int heard = 0;
                while (waited < l->cfg.relay_wait_ms && !heard) {
                    heard = rx_once(l, l->cfg.relay_wait_ms - waited, dl, now_unix, f.seq, 0, 1);
                    waited = l->hal->now_ms(l->hal->ctx) - t0;
                }
                if (!heard) {
                    ffp_frame_t g = f;
                    g.flags = (uint8_t)(g.flags | FFP_F_RELAYED);
                    if (send_frame(l, &g) == 0) l->st->relayed_count++;
                }
            }
        }
    }
    return 0;
}

int box_link_send_priority(box_link_t *l, uint8_t type, uint8_t flags, const ffp_status_t *s, int repeats,
                           bool *acked, box_downlinks_t *dl, int64_t now_unix)
{
    int i, sent = 0;
    uint8_t seq = l->st->seq++;
    if (acked) *acked = false;
    if (repeats < 1) repeats = 1;
    if (repeats > 4) repeats = 4;
    for (i = 0; i < repeats; i++) {
        ffp_frame_t f;
        ffp_status_t c = *s;
        c.repeat = (uint8_t)(i > 3 ? 3 : i);
        ffp_frame_init(&f, type, (uint8_t)(flags | FFP_F_ACK_REQ | FFP_F_PRIORITY), l->my_id, FFP_ID_ANY_GW, seq);
        ffp_pack_status(&f, &c);
        if (send_frame(l, &f) == 0) sent++;
        {
            uint32_t jitter = l->hal->random32 ? (l->hal->random32(l->hal->ctx) % 200u) : 0u;
            uint32_t t0 = l->hal->now_ms(l->hal->ctx), wait = l->cfg.alert_gap_ms + jitter, waited = 0;
            int got = 0;
            while (waited < wait && !got) {
                got = rx_once(l, wait - waited, dl, now_unix, seq, type, 0);
                waited = l->hal->now_ms(l->hal->ctx) - t0;
                if (got) break;
            }
            if (got) { if (acked) *acked = true; break; }
        }
    }
    return sent;
}

static uint8_t enqueue(box_link_t *l, const ffp_frame_t *proto)
{
    box_link_state_t *s = l->st;
    ffp_frame_t f = *proto;
    uint8_t seq = s->seq++;
    f.seq = seq;
    if (s->n >= BOX_QN) {                       /* full: drop the oldest heartbeat or telemetry, else the oldest frame */
        int i, drop = 0;
        for (i = 0; i < s->n; i++) {
            uint8_t t = (uint8_t)(s->q[i].bytes[0] >> 4);
            if (t == FFP_T_HEARTBEAT || t == FFP_T_TELEM) { drop = i; break; }
        }
        memmove(&s->q[drop], &s->q[drop + 1], (size_t)(s->n - drop - 1) * sizeof s->q[0]);
        s->n--;
        s->dropped_count++;
    }
    ffp_encode(&f, s->q[s->n].bytes);
    s->n++;
    return seq;
}

uint8_t box_link_queue_status(box_link_t *l, uint8_t type, uint8_t flags, const ffp_status_t *st)
{
    ffp_frame_t f;
    ffp_frame_init(&f, type, (uint8_t)(flags | FFP_F_ACK_REQ), l->my_id, FFP_ID_ANY_GW, 0);
    ffp_pack_status(&f, st);
    return enqueue(l, &f);
}

uint8_t box_link_queue_telem(box_link_t *l, uint8_t flags, const ffp_telem_t *t)
{
    ffp_frame_t f;
    ffp_frame_init(&f, FFP_T_TELEM, (uint8_t)(flags | FFP_F_ACK_REQ), l->my_id, FFP_ID_ANY_GW, 0);
    ffp_pack_telem(&f, t);
    return enqueue(l, &f);
}

uint8_t box_link_queue_pos(box_link_t *l, uint8_t flags, const ffp_pos_t *p)
{
    ffp_frame_t f;
    ffp_frame_init(&f, FFP_T_POS, (uint8_t)(flags | FFP_F_ACK_REQ), l->my_id, FFP_ID_ANY_GW, 0);
    ffp_pack_pos(&f, p);
    return enqueue(l, &f);
}

int box_link_flush(box_link_t *l, box_downlinks_t *dl, int64_t now_unix)
{
    box_link_state_t *s = l->st;
    int done = 0;
    while (s->n > 0 && done < l->cfg.max_flush) {
        uint8_t *b = s->q[0].bytes;
        uint8_t seq = b[2], type = (uint8_t)(b[0] >> 4);
        int t, got = 0;
        for (t = 0; t < l->cfg.routine_tries && !got; t++) {
            uint32_t t0, waited = 0;
            send_raw(l, b);
            t0 = l->hal->now_ms(l->hal->ctx);
            while (waited < l->cfg.ack_wait_ms && !got) {
                got = rx_once(l, l->cfg.ack_wait_ms - waited, dl, now_unix, seq, type, 0);
                waited = l->hal->now_ms(l->hal->ctx) - t0;
            }
        }
        if (!got) break;                         /* gateway unreachable: keep the rest for the next wake-up */
        memmove(&s->q[0], &s->q[1], (size_t)(s->n - 1) * sizeof s->q[0]);
        s->n--;
        done++;
    }
    return done;
}

void box_link_listen(box_link_t *l, uint32_t window_ms, box_downlinks_t *dl, int64_t now_unix)
{
    uint32_t t0 = l->hal->now_ms(l->hal->ctx), waited = 0;
    while (waited < window_ms) {
        rx_once(l, window_ms - waited, dl, now_unix, -1, 0, 0);
        waited = l->hal->now_ms(l->hal->ctx) - t0;
        if (waited == 0) waited = 1;             /* a mock that does not advance time must not loop forever */
    }
}
