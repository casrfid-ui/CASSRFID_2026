#include "sim800.h"

#include <stdio.h>
#include <string.h>
#include <stdlib.h>

static int wr(sim800_t *m, const char *s) { return m->io.write(m->io.ctx, (const uint8_t *)s, strlen(s)); }

/* Sends a command and waits for OK; keeps the last non-empty line before OK in `last` (may be NULL). */
static int cmd(sim800_t *m, const char *c, char *last, size_t lcap, uint32_t timeout_ms)
{
    char line[96];
    int i;
    if (last && lcap) last[0] = 0;
    wr(m, c); wr(m, "\r");
    for (i = 0; i < 12; i++) {
        int n = m->io.read_line(m->io.ctx, line, sizeof line, timeout_ms);
        if (n <= 0) return -1;
        if (strcmp(line, "OK") == 0) return 0;
        if (strstr(line, "ERROR")) return -2;
        if (last && lcap && strncmp(line, "AT", 2) != 0) { snprintf(last, lcap, "%s", line); }
    }
    return -1;
}

int sim800_init(sim800_t *m, const sim_io_t *io)
{
    char l[96];
    int tries;
    if (!m || !io || !io->write || !io->read_line) return SIM_E_ARG;
    memset(m, 0, sizeof *m);
    m->io = *io;
    m->csq = 99;
    for (tries = 0; tries < 3; tries++) if (cmd(m, "AT", NULL, 0, 500) == 0) break;
    if (tries == 3) return SIM_E_NO_MODEM;
    cmd(m, "ATE0", NULL, 0, 500);
    if (cmd(m, "AT+CMGF=1", NULL, 0, 1000) != 0) return SIM_E_NO_MODEM;
    for (tries = 0; tries < 10; tries++) {                       /* registration can take a while after power-on */
        int stat = -1, n;
        if (cmd(m, "AT+CREG?", l, sizeof l, 1000) == 0 && (n = sscanf(l, "+CREG: %*d,%d", &stat)) == 1 && (stat == 1 || stat == 5)) break;
        if (m->io.delay_ms) m->io.delay_ms(m->io.ctx, 1000);
    }
    if (tries == 10) return SIM_E_NO_NETWORK;
    if (cmd(m, "AT+CSQ", l, sizeof l, 1000) == 0) { int q; if (sscanf(l, "+CSQ: %d", &q) == 1) m->csq = q; }
    m->ready = true;
    return SIM_OK;
}

int sim800_send_sms(sim800_t *m, const char *number, const char *text)
{
    char line[96], c[48];
    uint8_t ctrlz = 0x1A;
    char body[161];
    size_t i, n = 0;
    int k;
    if (!m || !number || !text || number[0] != '+' || strlen(number) < 8 || strlen(number) > 20) return SIM_E_ARG;
    for (i = 0; number[i]; i++) if (i > 0 && (number[i] < '0' || number[i] > '9')) return SIM_E_ARG;
    if (!m->ready) return SIM_E_NO_NETWORK;
    for (i = 0; text[i] && n < 160; i++) body[n++] = (text[i] >= 0x20 && text[i] <= 0x7E) ? text[i] : (text[i] == '\n' ? '\n' : '?');
    body[n] = 0;
    snprintf(c, sizeof c, "AT+CMGS=\"%s\"", number);
    wr(m, c); wr(m, "\r");
    for (k = 0; k < 5; k++) {
        int r = m->io.read_line(m->io.ctx, line, sizeof line, 3000);
        if (r <= 0) return SIM_E_PROMPT;
        if (line[0] == '>') break;
        if (strstr(line, "ERROR")) return SIM_E_PROMPT;
    }
    if (k == 5) return SIM_E_PROMPT;
    m->io.write(m->io.ctx, (const uint8_t *)body, n);
    m->io.write(m->io.ctx, &ctrlz, 1);
    for (k = 0; k < 6; k++) {                                    /* "+CMGS: n" then OK, up to 60 s on a busy network */
        int r = m->io.read_line(m->io.ctx, line, sizeof line, 20000);
        if (r <= 0) return SIM_E_SEND;
        if (strstr(line, "ERROR")) return SIM_E_SEND;
        if (strcmp(line, "OK") == 0) return SIM_OK;
    }
    return SIM_E_SEND;
}
