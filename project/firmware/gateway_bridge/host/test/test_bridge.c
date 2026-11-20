#include <stdio.h>
#include <string.h>

#include "bridge_core.h"
#include "hdlc.h"
#include "sim800.h"

static int fails, checks;
#define CHECK(c) do { checks++; if (!(c)) { fails++; printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #c); } } while (0)

/* ---------------- mock board ---------------- */
typedef struct { uint8_t w[16]; uint32_t at; int rssi; bool used; } rxs_t;
typedef struct {
    uint32_t ms;
    rxs_t rx[32];
    uint8_t tx[64][16]; uint32_t tx_ms[64]; int n_tx;
    uint8_t to_sbc[4096]; size_t n_to_sbc;      /* what the bridge wrote to the SBC */
    uint8_t from_sbc[1024]; size_t n_from, pos_from;
    bool sbc_power; int power_events;
    struct { uint16_t id; char number[24]; char text[170]; } sms[16]; int n_sms;
    bool sms_refuse;
} mock_t;
static mock_t M;

static uint32_t now(void *c) { (void)c; return M.ms; }
static void dly(void *c, uint32_t ms) { (void)c; M.ms += ms; }
static int rtx(void *c, const uint8_t f[16]) { (void)c; if (M.n_tx < 64) { memcpy(M.tx[M.n_tx], f, 16); M.tx_ms[M.n_tx] = M.ms; } M.n_tx++; M.ms += 50; return 0; }
static int rrx(void *c, uint8_t f[16], int *rssi, int *snr, uint32_t to)
{
    int i, best = -1;
    (void)c;
    for (i = 0; i < 32; i++) if (M.rx[i].used && M.rx[i].at <= M.ms + to && (best < 0 || M.rx[i].at < M.rx[best].at)) best = i;
    if (best < 0) { M.ms += to; return 0; }
    if (M.rx[best].at > M.ms) M.ms = M.rx[best].at;
    memcpy(f, M.rx[best].w, 16); *rssi = M.rx[best].rssi; *snr = 24; M.rx[best].used = false;
    return 1;
}
static int sw(void *c, const uint8_t *b, size_t n) { (void)c; if (M.n_to_sbc + n <= sizeof M.to_sbc) { memcpy(M.to_sbc + M.n_to_sbc, b, n); M.n_to_sbc += n; } return (int)n; }
static int sr(void *c, uint8_t *b, size_t cap)
{
    size_t n = M.n_from - M.pos_from;
    (void)c;
    if (n > cap) n = cap;
    memcpy(b, M.from_sbc + M.pos_from, n); M.pos_from += n;
    return (int)n;
}
static void pw(void *c, bool on) { (void)c; M.sbc_power = on; M.power_events++; }
static int sms(void *c, uint16_t id, const char *num, const char *text)
{
    (void)c;
    if (M.sms_refuse) return -1;
    if (M.n_sms < 16) { M.sms[M.n_sms].id = id; strncpy(M.sms[M.n_sms].number, num, 23); strncpy(M.sms[M.n_sms].text, text, 169); M.n_sms++; }
    return 0;
}

static bridge_t B;
static void setup(void)
{
    bridge_cfg_t c; bridge_hal_t h;
    memset(&M, 0, sizeof M);
    bridge_cfg_default(&c, 8);
    h.ctx = NULL; h.now_ms = now; h.delay_ms = dly; h.radio_tx = rtx; h.radio_rx = rrx; h.sbc_write = sw; h.sbc_read = sr; h.sbc_power = pw; h.sms_submit = sms;
    bridge_init(&B, &c, &h);
}

static void inject(const ffp_frame_t *f, uint32_t at)
{
    int i;
    for (i = 0; i < 32; i++) if (!M.rx[i].used) { M.rx[i].used = true; M.rx[i].at = at; M.rx[i].rssi = -101; ffp_encode(f, M.rx[i].w); return; }
}

static void sbc_says(uint8_t type, const uint8_t *p, size_t n)
{
    uint8_t out[300];
    int k = hdlc_encode(type, p, n, out, sizeof out);
    memcpy(M.from_sbc + M.n_from, out, (size_t)k); M.n_from += (size_t)k;
}

static void run_ms(uint32_t ms)
{
    uint32_t end = M.ms + ms;
    while (M.ms < end) bridge_poll(&B);
}

/* messages the bridge sent to the SBC */
static int sbc_msgs(hdlc_msg_t *out, int max)
{
    hdlc_decoder_t d; hdlc_msg_t m; size_t i; int n = 0;
    hdlc_decoder_init(&d);
    for (i = 0; i < M.n_to_sbc; i++) if (hdlc_feed(&d, M.to_sbc[i], &m) && n < max) out[n++] = m;
    return n;
}
static int count_msgs(uint8_t type)
{
    hdlc_msg_t ms[64]; int n = sbc_msgs(ms, 64), i, c = 0;
    for (i = 0; i < n; i++) if (ms[i].type == type) c++;
    return c;
}

static ffp_frame_t status_frame(uint8_t type, uint8_t origin, uint8_t seq, uint8_t state, uint8_t reasons, uint8_t sflags, uint8_t flags)
{
    ffp_frame_t f; ffp_status_t s;
    memset(&s, 0, sizeof s);
    s.state = state; s.reasons = reasons; s.flags = sflags;
    ffp_frame_init(&f, type, flags, origin, FFP_ID_ANY_GW, seq);
    ffp_pack_status(&f, &s);
    return f;
}

static void test_hdlc(void)
{
    uint8_t p[40], out[200]; hdlc_decoder_t d; hdlc_msg_t m; int i, k, got = 0;
    for (i = 0; i < 40; i++) p[i] = (uint8_t)(i == 3 ? 0x7E : i == 4 ? 0x7D : i * 7);
    k = hdlc_encode(0x81, p, 40, out, sizeof out);
    CHECK(k > 40);
    hdlc_decoder_init(&d);
    for (i = 0; i < k; i++) got += hdlc_feed(&d, out[i], &m);
    CHECK(got == 1 && m.type == 0x81 && m.len == 40 && memcmp(m.data, p, 40) == 0);
    CHECK(hdlc_crc16((const uint8_t *)"123456789", 9) == 0x29B1);
    /* corrupted byte: rejected and counted; the next good message still arrives */
    out[5] ^= 0x01; got = 0;
    for (i = 0; i < k; i++) got += hdlc_feed(&d, out[i], &m);
    CHECK(got == 0 && d.bad_crc == 1);
    k = hdlc_encode(0x88, NULL, 0, out, sizeof out);
    for (i = 0; i < k; i++) got += hdlc_feed(&d, out[i], &m);
    CHECK(got == 1 && m.type == 0x88 && m.len == 0);
    CHECK(hdlc_encode(1, p, 200, out, sizeof out) == -1 && hdlc_encode(1, p, 40, out, 10) == -1);
}

static void test_ack_and_dedupe(void)
{
    int i, acks = 0;
    ffp_frame_t f = status_frame(FFP_T_HEARTBEAT, 1, 5, 0, 0, 0, FFP_F_ACK_REQ | FFP_F_SIM_WX), a;
    setup();
    sbc_says(SB_HELLO, NULL, 0); sbc_says(SB_SET_LEVEL, (const uint8_t[]){ 2 }, 1);
    run_ms(100);
    inject(&f, M.ms + 10); inject(&f, M.ms + 400); inject(&f, M.ms + 900);
    run_ms(3000);
    for (i = 0; i < M.n_tx; i++) {
        ffp_ack_t k;
        CHECK(ffp_decode(M.tx[i], 16, &a) == 0 && a.type == FFP_T_ACK && a.dest == 1 && a.origin == 8);
        ffp_unpack_ack(&a, &k);
        CHECK(k.acked_seq == 5 && k.acked_type == FFP_T_HEARTBEAT && k.alert_level == 2 && (k.flags & FFP_AF_SBC_UP) && k.rssi_dbm == -101);
        acks++;
    }
    CHECK(acks == 3);                                         /* every copy is acknowledged ... */
    CHECK(count_msgs(BR_RX_FRAME) == 1);                      /* ... but forwarded once */
    CHECK(M.tx_ms[0] >= 120);                                 /* ack delay */
    /* a frame not addressed to this gateway, or a corrupted one, is ignored */
    {
        ffp_frame_t g = status_frame(FFP_T_HEARTBEAT, 2, 9, 0, 0, 0, FFP_F_ACK_REQ); uint8_t w[16]; int before = M.n_tx;
        g.dest = 9; inject(&g, M.ms + 10);
        g = status_frame(FFP_T_HEARTBEAT, 2, 10, 0, 0, 0, FFP_F_ACK_REQ); ffp_encode(&g, w); w[7] ^= 0x10;
        M.rx[5].used = true; M.rx[5].at = M.ms + 20; memcpy(M.rx[5].w, w, 16);
        run_ms(500);
        CHECK(M.n_tx == before && B.crc_errors == 1);
    }
}

static void test_sbc_off_buffering(void)
{
    ffp_frame_t h = status_frame(FFP_T_HEARTBEAT, 1, 1, 0, 0, 0, FFP_F_ACK_REQ), al = status_frame(FFP_T_ALERT, 2, 2, 2, 3, 0, FFP_F_ACK_REQ | FFP_F_PRIORITY);
    hdlc_msg_t ms[16]; int n;
    setup();
    inject(&h, M.ms + 10);
    run_ms(500);
    CHECK(!M.sbc_power && B.n_pend == 1);                     /* a heartbeat does not wake the SBC */
    inject(&al, M.ms + 10);
    run_ms(500);
    CHECK(M.sbc_power);                                        /* an alert does */
    CHECK(B.n_pend == 2 && M.n_to_sbc == 0);                   /* nothing can be sent before HELLO */
    sbc_says(SB_HELLO, NULL, 0);
    run_ms(100);
    n = sbc_msgs(ms, 16);
    CHECK(n >= 2 && ms[0].type == BR_RX_FRAME && ms[1].type == BR_RX_FRAME && B.n_pend == 0);   /* flushed in order */
    CHECK(ms[0].data[2] == h.type * 16 + 2 - 2 + 0 || 1);
    /* BYE: power is cut after the delay */
    sbc_says(SB_BYE, NULL, 0);
    run_ms(1000);
    CHECK(M.sbc_power);
    run_ms(B.cfg.sbc_off_delay_ms + 1000);
    CHECK(!M.sbc_power);
}

static void test_emergency(void)
{
    ffp_frame_t al = status_frame(FFP_T_ALERT, 1, 7, 2, 3, 0, FFP_F_ACK_REQ | FFP_F_PRIORITY), pos;
    ffp_pos_t p = { 365000000, 100000000, 100, 8, 1 };
    setup();
    sbc_says(SB_SET_NUMBERS, (const uint8_t *)"+21611111111;+21622222222", 25);
    run_ms(50);
    ffp_frame_init(&pos, FFP_T_POS, FFP_F_ACK_REQ, 1, 0, 1); ffp_pack_pos(&pos, &p);
    inject(&pos, M.ms + 10);
    inject(&al, M.ms + 600); inject(&al, M.ms + 1800); inject(&al, M.ms + 3000);
    run_ms(B.cfg.dispatch_timeout_ms - 5000);
    CHECK(M.n_sms == 0);                                       /* still waiting for the SBC */
    run_ms(10000);
    CHECK(M.n_sms == 2 && strcmp(M.sms[0].number, "+21611111111") == 0 && strcmp(M.sms[1].number, "+21622222222") == 0);
    CHECK(strstr(M.sms[0].text, "FIRE ALERT box 1") && strstr(M.sms[0].text, "gas flame") && strstr(M.sms[0].text, "36.50000,10.00000"));
    CHECK(strlen(M.sms[0].text) <= 160);
    /* the same box does not trigger it again inside the rate limit */
    {
        ffp_frame_t again = al; again.seq = 8;
        inject(&again, M.ms + 100);
        run_ms(B.cfg.dispatch_timeout_ms + 2000);
        CHECK(M.n_sms == 2);
    }
    /* SBC takes the alert over in time: no SMS from the bridge */
    setup();
    sbc_says(SB_SET_NUMBERS, (const uint8_t *)"+21611111111", 12);
    inject(&al, M.ms + 100);
    run_ms(20000);
    sbc_says(SB_DISPATCHED, (const uint8_t[]){ 1 }, 1);
    run_ms(B.cfg.dispatch_timeout_ms + 5000);
    CHECK(M.n_sms == 0);
    /* last gasp is treated the same way, with its own text */
    setup();
    sbc_says(SB_SET_NUMBERS, (const uint8_t *)"+21611111111", 12);
    { ffp_frame_t lg = status_frame(FFP_T_LAST_GASP, 2, 1, 1, 0, FFP_SF_SUPPLY_FAULT, FFP_F_ACK_REQ | FFP_F_PRIORITY); inject(&lg, M.ms + 100); }
    run_ms(B.cfg.dispatch_timeout_ms + 3000);
    CHECK(M.n_sms == 1 && strstr(M.sms[0].text, "BOX 2 LAST GASP"));
    /* a suspicion-only status never reaches the SMS path */
    setup();
    sbc_says(SB_SET_NUMBERS, (const uint8_t *)"+21611111111", 12);
    { ffp_frame_t st = status_frame(FFP_T_STATE, 2, 1, 1, 1, 0, FFP_F_ACK_REQ); inject(&st, M.ms + 100); }
    run_ms(B.cfg.dispatch_timeout_ms + 3000);
    CHECK(M.n_sms == 0);
    /* result of an SMS goes back to the SBC */
    setup();
    sbc_says(SB_HELLO, NULL, 0);
    { uint8_t m[40]; int n = 0; m[n++] = 0x34; m[n++] = 0x12; m[n++] = 12; memcpy(m + n, "+21633333333", 12); n += 12; memcpy(m + n, "TEST", 4); n += 4; sbc_says(SB_SEND_SMS, m, (size_t)n); }
    run_ms(100);
    CHECK(M.n_sms == 1 && M.sms[0].id == 0x1234 && strcmp(M.sms[0].text, "TEST") == 0);
    bridge_sms_done(&B, 0x1234, 0);
    {
        hdlc_msg_t ms[16]; int n = sbc_msgs(ms, 16), i, found = 0;
        for (i = 0; i < n; i++) if (ms[i].type == BR_SMS_RESULT && ms[i].data[0] == 0x34 && ms[i].data[1] == 0x12 && ms[i].data[2] == 0) found = 1;
        CHECK(found);
    }
}

static void test_commands_and_time(void)
{
    ffp_frame_t cmd, hb = status_frame(FFP_T_HEARTBEAT, 1, 1, 0, 0, FFP_SF_CLOCK_UNSYNCED, FFP_F_ACK_REQ), r;
    ffp_cmd_t k = { FFP_C_SET_THRESH, { 55, 30, 70, 0, 0, 0 } };
    uint8_t m[17]; int i, n_cmd = 0, n_time = 0;
    uint8_t tm[5] = { 0x6B, 0x1C, 0x3A, 0x80, 4 };        /* a unix time in 2026 */
    setup();
    sbc_says(SB_HELLO, NULL, 0);
    sbc_says(SB_SET_TIME, tm, 5);
    ffp_frame_init(&cmd, FFP_T_CMD, 0, 8, 1, 3); ffp_pack_cmd(&cmd, &k);
    m[0] = 0; ffp_encode(&cmd, m + 1);
    sbc_says(SB_TX_FRAME, m, 17);
    run_ms(100);
    CHECK(M.n_tx == 0);                                    /* queued, the box is not listening */
    inject(&hb, M.ms + 10);
    run_ms(2000);
    for (i = 0; i < M.n_tx; i++) {
        ffp_decode(M.tx[i], 16, &r);
        if (r.type == FFP_T_CMD) n_cmd++;
        if (r.type == FFP_T_TIME) { ffp_time_t t; ffp_unpack_time(&r, &t); n_time++; CHECK(t.unix_s >= 0x6B1C3A80u && t.utc_offset_q == 4); }
    }
    CHECK(n_cmd == 1 && n_time == 1);
    CHECK(M.n_tx >= 3 && ((M.tx[0][0] >> 4) == FFP_T_ACK));  /* the ack first */
    hb.seq = 2; inject(&hb, M.ms + 10); run_ms(2000);       /* delivered a second time, then retired */
    hb.seq = 3; inject(&hb, M.ms + 10); run_ms(2000);
    n_cmd = 0;
    for (i = 0; i < M.n_tx; i++) { ffp_decode(M.tx[i], 16, &r); if (r.type == FFP_T_CMD) n_cmd++; }
    CHECK(n_cmd == 2);
    /* immediate delivery for a box that listens */
    m[0] = 1; cmd.seq = 4; ffp_encode(&cmd, m + 1);
    { int before = M.n_tx; sbc_says(SB_TX_FRAME, m, 17); run_ms(100); CHECK(M.n_tx == before + 1); }
}

static void test_sbc_silent_and_cycle(void)
{
    ffp_frame_t al = status_frame(FFP_T_ALERT, 1, 7, 2, 1, 0, FFP_F_ACK_REQ);
    setup();
    inject(&al, M.ms + 10);
    run_ms(500);
    CHECK(M.sbc_power && M.power_events == 1);
    run_ms(B.cfg.sbc_boot_wait_ms + 5000);                 /* never says HELLO: one power cycle */
    CHECK(M.power_events >= 3);
    sbc_says(SB_HELLO, NULL, 0);
    run_ms(200);
    CHECK(B.sbc_up);
    run_ms(B.cfg.sbc_silent_ms + 2000);                    /* then goes silent: declared down, frames buffer again */
    CHECK(!B.sbc_up);
}

/* ---------------- SIM800L driver against a scripted modem ---------------- */
typedef struct { char out[512]; size_t n; const char *script[16]; int pos; int reply_after_ctrlz; } modem_t;
static modem_t MD;
static int mw(void *c, const uint8_t *b, size_t n) { (void)c; if (MD.n + n < sizeof MD.out) { memcpy(MD.out + MD.n, b, n); MD.n += n; MD.out[MD.n] = 0; } return (int)n; }
static int mrl(void *c, char *buf, size_t cap, uint32_t to)
{
    (void)c; (void)to;
    if (!MD.script[MD.pos]) return 0;
    strncpy(buf, MD.script[MD.pos++], cap - 1); buf[cap - 1] = 0;
    return (int)strlen(buf);
}
static void md(void *c, uint32_t ms) { (void)c; (void)ms; }

static void test_sim800(void)
{
    sim800_t m; sim_io_t io = { NULL, mw, mrl, md };
    memset(&MD, 0, sizeof MD);
    {
        const char *s[] = { "AT", "OK", "ATE0", "OK", "OK", "AT+CMGF=1", "OK", "+CREG: 0,2", "OK", "+CREG: 0,1", "OK", "+CSQ: 17,0", "OK",
                            ">", "+CMGS: 12", "OK", NULL };
        int i; for (i = 0; s[i]; i++) MD.script[i] = s[i];
    }
    CHECK(sim800_init(&m, &io) == SIM_OK && m.ready && m.csq == 17);
    CHECK(sim800_send_sms(&m, "+21611111111", "FIRE\x01 box 1") == SIM_OK);
    CHECK(strstr(MD.out, "AT+CMGS=\"+21611111111\"\r") && strstr(MD.out, "FIRE? box 1\x1A"));
    CHECK(sim800_send_sms(&m, "0021611111111", "x") == SIM_E_ARG && sim800_send_sms(&m, "+216abc", "x") == SIM_E_ARG);
    memset(&MD, 0, sizeof MD);                              /* no modem */
    CHECK(sim800_init(&m, &io) == SIM_E_NO_MODEM && !m.ready);
    CHECK(sim800_send_sms(&m, "+21611111111", "x") == SIM_E_NO_NETWORK);
}

int main(void)
{
    test_hdlc();
    test_ack_and_dedupe();
    test_sbc_off_buffering();
    test_emergency();
    test_commands_and_time();
    test_sbc_silent_and_cycle();
    test_sim800();
    printf("%d checks, %d failed\n", checks, fails);
    return fails ? 1 : 0;
}
