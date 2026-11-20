#include "bridge_core.h"

#include <stdio.h>
#include <string.h>

void bridge_cfg_default(bridge_cfg_t *c, uint8_t gw_id)
{
    c->gw_id = gw_id;
    c->ack_delay_ms = 120;
    c->cmd_gap_ms = 350;
    c->radio_poll_ms = 25;
    c->sbc_silent_ms = 120000;
    c->sbc_boot_wait_ms = 90000;
    c->sbc_off_delay_ms = 20000;
    c->sbc_periodic_wake_ms = 3600000;
    c->sbc_wake_pending = 8;
    c->dispatch_timeout_ms = 60000;
    c->sms_rate_limit_ms = 900000;
    c->status_period_ms = 30000;
    c->cmd_max_age_ms = 1800000;
}

void bridge_init(bridge_t *b, const bridge_cfg_t *cfg, const bridge_hal_t *hal)
{
    memset(b, 0, sizeof *b);
    b->cfg = *cfg;
    b->hal = *hal;
    hdlc_decoder_init(&b->dec);
}

void bridge_set_modem_state(bridge_t *b, bool ready, uint8_t csq) { b->modem_ready = ready; b->csq = csq; }

static void sbc_send(bridge_t *b, uint8_t type, const uint8_t *p, size_t n)
{
    uint8_t out[2 * (HDLC_MAX_PAYLOAD + 3) + 2];
    int k = hdlc_encode(type, p, n, out, sizeof out);
    if (k > 0 && b->sbc_powered) b->hal.sbc_write(b->hal.ctx, out, (size_t)k);
}

static void forward(bridge_t *b, const uint8_t w[FFP_FRAME_LEN], int rssi, int snr)
{
    uint8_t m[2 + FFP_FRAME_LEN];
    m[0] = (uint8_t)(int8_t)(rssi < -128 ? -128 : rssi > 127 ? 127 : rssi);
    m[1] = (uint8_t)(int8_t)(snr < -128 ? -128 : snr > 127 ? 127 : snr);
    memcpy(m + 2, w, FFP_FRAME_LEN);
    sbc_send(b, BR_RX_FRAME, m, sizeof m);
    b->forwarded++;
}

static void sbc_power_on(bridge_t *b)
{
    if (b->sbc_powered) return;
    b->hal.sbc_power(b->hal.ctx, true);
    b->sbc_powered = true;
    b->sbc_up = false;
    b->sbc_power_on_ms = b->hal.now_ms(b->hal.ctx);
    b->sbc_cycled = false;
    b->sbc_bye_ms = 0;
}

static void pend_push(bridge_t *b, const uint8_t w[FFP_FRAME_LEN], int rssi, int snr, bool prio)
{
    br_pending_t *p;
    if (b->n_pend >= BR_PEND_MAX) {                 /* full: drop the oldest routine frame, else the oldest */
        uint8_t i, drop = 0;
        for (i = 0; i < b->n_pend; i++) if (!b->pend[i].priority) { drop = i; break; }
        memmove(&b->pend[drop], &b->pend[drop + 1], (size_t)(b->n_pend - drop - 1) * sizeof b->pend[0]);
        b->n_pend--;
    }
    p = &b->pend[b->n_pend++];
    memcpy(p->bytes, w, FFP_FRAME_LEN);
    p->rssi = (int8_t)rssi; p->snr = (int8_t)snr; p->priority = prio;
}

static void flush_pending(bridge_t *b)
{
    uint8_t i;
    for (i = 0; i < b->n_pend; i++) forward(b, b->pend[i].bytes, b->pend[i].rssi, b->pend[i].snr);
    b->n_pend = 0;
}

static bool seen(bridge_t *b, uint8_t o, uint8_t s, uint8_t t)
{
    int i;
    for (i = 0; i < BR_SEEN; i++) if (b->seen[i][0] == o && b->seen[i][1] == s && b->seen[i][2] == t) return true;
    return false;
}

static void remember(bridge_t *b, uint8_t o, uint8_t s, uint8_t t)
{
    b->seen[b->seen_pos][0] = o; b->seen[b->seen_pos][1] = s; b->seen[b->seen_pos][2] = t;
    b->seen_pos = (uint8_t)((b->seen_pos + 1) % BR_SEEN);
}

static int64_t unix_now(const bridge_t *b)
{
    if (!b->have_time) return -1;
    return (int64_t)b->time_unix_base + (int64_t)((b->hal.now_ms(b->hal.ctx) - b->time_base_ms) / 1000u);
}

static void send_ack(bridge_t *b, const ffp_frame_t *f, int rssi, int snr)
{
    ffp_frame_t a;
    ffp_ack_t k;
    uint8_t w[FFP_FRAME_LEN];
    memset(&k, 0, sizeof k);
    k.acked_seq = f->seq; k.acked_type = f->type;
    k.flags = (uint8_t)(FFP_AF_FROM_BRIDGE | (b->sbc_up ? FFP_AF_SBC_UP : 0));
    k.rssi_dbm = (int8_t)(rssi < -128 ? -128 : rssi > 0 ? 0 : rssi);
    k.snr_x4 = (int8_t)(snr < -128 ? -128 : snr > 127 ? 127 : snr);
    k.gw_id = b->cfg.gw_id; k.alert_level = b->level;
    ffp_frame_init(&a, FFP_T_ACK, 0, b->cfg.gw_id, f->origin, 0);
    ffp_pack_ack(&a, &k);
    if (ffp_encode(&a, w) == 0) { b->hal.radio_tx(b->hal.ctx, w); b->acks_tx++; }
}

static void send_time(bridge_t *b, uint8_t dest)
{
    ffp_frame_t t;
    ffp_time_t tm;
    uint8_t w[FFP_FRAME_LEN];
    int64_t u = unix_now(b);
    if (u < 0) return;
    tm.unix_s = (uint32_t)u; tm.utc_offset_q = b->time_offset_q;
    ffp_frame_init(&t, FFP_T_TIME, 0, b->cfg.gw_id, dest, b->time_seq++);
    ffp_pack_time(&t, &tm);
    if (ffp_encode(&t, w) == 0) b->hal.radio_tx(b->hal.ctx, w);
}

static void deliver_cmds(bridge_t *b, uint8_t box)
{
    uint8_t i = 0, sent = 0;
    uint32_t now = b->hal.now_ms(b->hal.ctx);
    while (i < b->n_cmd[box]) {                       /* drop the old ones first */
        if (now - b->cmdq[box][i].born_ms > b->cfg.cmd_max_age_ms) {
            memmove(&b->cmdq[box][i], &b->cmdq[box][i + 1], (size_t)(b->n_cmd[box] - i - 1) * sizeof b->cmdq[0][0]);
            b->n_cmd[box]--;
        } else i++;
    }
    for (i = 0; i < b->n_cmd[box] && sent < 2; i++) {
        b->hal.delay_ms(b->hal.ctx, b->cfg.cmd_gap_ms);
        b->hal.radio_tx(b->hal.ctx, b->cmdq[box][i].bytes);
        b->cmdq[box][i].deliveries++;
        sent++;
    }
    for (i = 0; i < b->n_cmd[box];) {                 /* delivered twice: retire */
        if (b->cmdq[box][i].deliveries >= 2) {
            memmove(&b->cmdq[box][i], &b->cmdq[box][i + 1], (size_t)(b->n_cmd[box] - i - 1) * sizeof b->cmdq[0][0]);
            b->n_cmd[box]--;
        } else i++;
    }
}

static void emergency_sms(bridge_t *b, uint8_t box, uint8_t type, const ffp_status_t *s)
{
    char text[161];
    char where[48] = "position unknown";
    char why[32] = "";
    uint32_t now = b->hal.now_ms(b->hal.ctx);
    uint8_t i;
    if (box > 7) return;
    if (b->sms_sent_once[box] && now - b->last_sms_ms[box] < b->cfg.sms_rate_limit_ms) return;
    if (b->have_pos[box])
        snprintf(where, sizeof where, "%.5f,%.5f", b->pos[box].lat_e7 / 1e7, b->pos[box].lon_e7 / 1e7);
    if (s->reasons & 1) strcat(why, "gas ");
    if (s->reasons & 2) strcat(why, "flame ");
    if (s->reasons & 4) strcat(why, "camera ");
    if (s->reasons & 8) strcat(why, "fwi ");
    if (type == FFP_T_LAST_GASP) snprintf(text, sizeof text, "BOX %u LAST GASP (supply or heat fault) - near %s. Sent by the gateway bridge: operator station offline.", box, where);
    else snprintf(text, sizeof text, "FIRE ALERT box %u - %sconfirmed by the box itself. Position %s. Sent by the gateway bridge: operator station offline.", box, why, where);
    b->sms_sent_once[box] = true;
    b->last_sms_ms[box] = now;
    for (i = 0; i < b->n_numbers; i++) b->hal.sms_submit(b->hal.ctx, (uint16_t)(0x8000u | (b->sms_counter++ & 0x7FFF)), b->numbers[i], text);
    b->emergencies++;
    {   /* tell the SBC (when it is up) so that it does not send the same SMS again */
        uint8_t m[3] = { box, type, b->n_numbers };
        sbc_send(b, BR_EMERGENCY, m, sizeof m);
    }
}

static void arm(bridge_t *b, const ffp_frame_t *f)
{
    br_armed_t *a;
    if (f->origin > 7) return;
    a = &b->armed[f->origin];
    if (a->active) return;
    a->active = true; a->origin = f->origin; a->seq = f->seq; a->type = f->type;
    a->deadline_ms = b->hal.now_ms(b->hal.ctx) + b->cfg.dispatch_timeout_ms;
    ffp_unpack_status(f, &b->last_status[f->origin]);
}

static void on_radio(bridge_t *b, const uint8_t w[FFP_FRAME_LEN], int rssi, int snr)
{
    ffp_frame_t f;
    bool dup, prio;
    b->frames_rx++;
    if (ffp_decode(w, FFP_FRAME_LEN, &f) != 0) { b->crc_errors++; return; }
    if (f.type == FFP_T_ACK || f.type == FFP_T_CMD || f.type == FFP_T_TIME) return;     /* another gateway's downlink */
    if (f.dest != FFP_ID_ANY_GW && f.dest != b->cfg.gw_id && f.dest != FFP_ID_BROADCAST) return;
    dup = seen(b, f.origin, f.seq, f.type);
    if (f.flags & FFP_F_ACK_REQ) {
        b->hal.delay_ms(b->hal.ctx, b->cfg.ack_delay_ms);
        send_ack(b, &f, rssi, snr);
        if (f.type <= FFP_T_LAST_GASP) {
            ffp_status_t s;
            ffp_unpack_status(&f, &s);
            if ((s.flags & FFP_SF_CLOCK_UNSYNCED) && b->have_time) { b->hal.delay_ms(b->hal.ctx, b->cfg.cmd_gap_ms); send_time(b, f.origin); }
        }
        if (f.origin <= 7) deliver_cmds(b, f.origin);
    }
    if (dup) return;
    remember(b, f.origin, f.seq, f.type);
    prio = f.type == FFP_T_ALERT || f.type == FFP_T_LAST_GASP || f.type == FFP_T_STATE;
    if (f.type == FFP_T_POS && f.origin <= 7) { ffp_unpack_pos(&f, &b->pos[f.origin]); b->have_pos[f.origin] = true; }
    if (f.type == FFP_T_ALERT || f.type == FFP_T_LAST_GASP) {
        ffp_status_t s;
        ffp_unpack_status(&f, &s);
        if (f.type == FFP_T_LAST_GASP || s.state == 2) arm(b, &f);
    }
    if (b->sbc_up) forward(b, w, rssi, snr);
    else {
        pend_push(b, w, rssi, snr, prio);
        if (prio || b->n_pend >= b->cfg.sbc_wake_pending) sbc_power_on(b);
    }
}

static void on_sbc(bridge_t *b, const hdlc_msg_t *m)
{
    b->sbc_last_rx_ms = b->hal.now_ms(b->hal.ctx);
    switch (m->type) {
    case SB_HELLO:
        b->sbc_up = true;
        b->sbc_powered = true;                         /* alive, whoever powered it */
        flush_pending(b);
        break;
    case SB_TX_FRAME:
        if (m->len == 1 + FFP_FRAME_LEN) {
            ffp_frame_t f;
            if (ffp_decode(m->data + 1, FFP_FRAME_LEN, &f) == 0 && f.dest <= 7 && f.dest >= 1) {
                br_cmd_t *c;
                if (b->n_cmd[f.dest] >= BR_CMDQ) {
                    memmove(&b->cmdq[f.dest][0], &b->cmdq[f.dest][1], (BR_CMDQ - 1) * sizeof b->cmdq[0][0]);
                    b->n_cmd[f.dest]--;
                }
                c = &b->cmdq[f.dest][b->n_cmd[f.dest]++];
                memcpy(c->bytes, m->data + 1, FFP_FRAME_LEN);
                c->deliveries = 0;
                c->born_ms = b->hal.now_ms(b->hal.ctx);
                if (m->data[0] & 1) {                    /* the box is known to be listening (Suspicion / Fire): send now */
                    b->hal.radio_tx(b->hal.ctx, c->bytes);
                    c->deliveries++;
                }
            }
        }
        break;
    case SB_SEND_SMS:
        if (m->len >= 5) {
            uint16_t id = (uint16_t)(m->data[0] | (m->data[1] << 8));
            uint8_t nl = m->data[2];
            char number[BR_NUMBER_LEN], text[161];
            size_t tl;
            if (nl >= 1 && nl < BR_NUMBER_LEN && (size_t)3 + nl <= m->len) {
                memcpy(number, m->data + 3, nl); number[nl] = 0;
                tl = m->len - 3 - nl;
                if (tl > 160) tl = 160;
                memcpy(text, m->data + 3 + nl, tl); text[tl] = 0;
                if (b->hal.sms_submit(b->hal.ctx, id, number, text) != 0) bridge_sms_done(b, id, 99);
            }
        }
        break;
    case SB_DISPATCHED:
        if (m->len >= 1 && m->data[0] <= 7) b->armed[m->data[0]].active = false;      /* the SBC took the alert of that box */
        break;
    case SB_BYE:
        b->sbc_up = false;
        b->sbc_bye_ms = b->hal.now_ms(b->hal.ctx);
        if (!b->sbc_bye_ms) b->sbc_bye_ms = 1;
        break;
    case SB_SET_NUMBERS: {
        size_t i = 0, k = 0;
        b->n_numbers = 0;
        while (i <= m->len && b->n_numbers < BR_NUMBERS) {
            if (i == m->len || m->data[i] == ';') {
                if (k > 0 && k < BR_NUMBER_LEN) { b->numbers[b->n_numbers][k] = 0; b->n_numbers++; }
                k = 0;
            } else if (k < BR_NUMBER_LEN - 1) b->numbers[b->n_numbers][k++] = (char)m->data[i];
            i++;
        }
        break;
    }
    case SB_SET_LEVEL:
        if (m->len >= 1) b->level = m->data[0] > 5 ? 5 : m->data[0];
        break;
    case SB_SET_TIME:
        if (m->len >= 5) {
            b->time_unix_base = ((uint32_t)m->data[0] << 24) | ((uint32_t)m->data[1] << 16) | ((uint32_t)m->data[2] << 8) | m->data[3];
            b->time_offset_q = (int8_t)m->data[4];
            b->time_base_ms = b->hal.now_ms(b->hal.ctx);
            b->have_time = b->time_unix_base > 1700000000u;
        }
        break;
    case SB_PING:
        b->last_status_ms = 0;                         /* answer with a status at the next pass */
        break;
    default: break;
    }
}

static void send_status(bridge_t *b)
{
    uint8_t m[13];
    uint32_t up = b->hal.now_ms(b->hal.ctx) / 1000u;
    uint8_t i, armed = 0;
    for (i = 0; i < 8; i++) if (b->armed[i].active) armed = 1;
    m[0] = (uint8_t)(up >> 24); m[1] = (uint8_t)(up >> 16); m[2] = (uint8_t)(up >> 8); m[3] = (uint8_t)up;
    m[4] = (uint8_t)((b->sbc_up ? 1 : 0) | (b->modem_ready ? 2 : 0) | (armed ? 4 : 0) | (b->have_time ? 8 : 0));
    m[5] = b->n_pend; m[6] = b->csq;
    m[7] = (uint8_t)(b->frames_rx >> 8); m[8] = (uint8_t)b->frames_rx;
    m[9] = (uint8_t)(b->acks_tx >> 8); m[10] = (uint8_t)b->acks_tx;
    m[11] = (uint8_t)(b->crc_errors >> 8); m[12] = (uint8_t)b->crc_errors;
    sbc_send(b, BR_STATUS, m, sizeof m);
}

void bridge_sms_done(bridge_t *b, uint16_t id, int status)
{
    uint8_t m[3];
    if (status == 0) b->sms_ok++; else b->sms_fail++;
    m[0] = (uint8_t)(id & 0xFF); m[1] = (uint8_t)(id >> 8); m[2] = (uint8_t)status;
    sbc_send(b, BR_SMS_RESULT, m, sizeof m);
}

void bridge_poll(bridge_t *b)
{
    uint8_t w[FFP_FRAME_LEN], buf[64];
    int rssi = 0, snr = 0, n, i;
    uint32_t now;
    hdlc_msg_t msg;

    if (b->hal.radio_rx(b->hal.ctx, w, &rssi, &snr, b->cfg.radio_poll_ms) == 1) on_radio(b, w, rssi, snr);

    while ((n = b->hal.sbc_read(b->hal.ctx, buf, sizeof buf)) > 0)
        for (i = 0; i < n; i++) if (hdlc_feed(&b->dec, buf[i], &msg)) on_sbc(b, &msg);

    now = b->hal.now_ms(b->hal.ctx);

    for (i = 0; i < 8; i++) {                                    /* fire alerts the SBC did not take over */
        if (b->armed[i].active && (int32_t)(now - b->armed[i].deadline_ms) >= 0) {
            b->armed[i].active = false;
            emergency_sms(b, (uint8_t)i, b->armed[i].type, &b->last_status[i]);
        }
    }
    if (b->sbc_powered) {
        if (b->sbc_up && now - b->sbc_last_rx_ms > b->cfg.sbc_silent_ms) b->sbc_up = false;       /* silent: declared down, frames buffer again */
        if (!b->sbc_up && b->sbc_bye_ms && now - b->sbc_bye_ms >= b->cfg.sbc_off_delay_ms) {
            b->hal.sbc_power(b->hal.ctx, false);
            b->sbc_powered = false; b->sbc_bye_ms = 0; b->last_periodic_ms = now;
        } else if (!b->sbc_up && !b->sbc_bye_ms && now - b->sbc_power_on_ms > b->cfg.sbc_boot_wait_ms && !b->sbc_cycled) {
            b->hal.sbc_power(b->hal.ctx, false);                 /* never said HELLO: one power cycle */
            b->hal.delay_ms(b->hal.ctx, 2000);
            b->hal.sbc_power(b->hal.ctx, true);
            b->sbc_cycled = true;
            b->sbc_power_on_ms = b->hal.now_ms(b->hal.ctx);
        }
    } else if (b->n_pend > 0 && b->cfg.sbc_periodic_wake_ms && now - b->last_periodic_ms >= b->cfg.sbc_periodic_wake_ms) {
        sbc_power_on(b);
    }
    if (b->sbc_up && now - b->last_status_ms >= b->cfg.status_period_ms) { send_status(b); b->last_status_ms = now; }
}
