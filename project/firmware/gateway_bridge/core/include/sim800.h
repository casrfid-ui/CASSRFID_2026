/* SIM800L AT driver: network check and text-mode SMS. C99, no heap. The UART is reached through sim_io_t (mocked in the tests). */
#ifndef SIM800_H
#define SIM800_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    void *ctx;
    int (*write)(void *ctx, const uint8_t *buf, size_t len);
    /* Reads one line (without CR/LF, may be empty lines skipped) into buf; returns its length, 0 on timeout. A bare "> " prompt is returned as ">". */
    int (*read_line)(void *ctx, char *buf, size_t cap, uint32_t timeout_ms);
    void (*delay_ms)(void *ctx, uint32_t ms);
} sim_io_t;

enum { SIM_OK = 0, SIM_E_NO_MODEM = 1, SIM_E_NO_NETWORK = 2, SIM_E_PROMPT = 3, SIM_E_SEND = 4, SIM_E_ARG = 5 };

typedef struct {
    sim_io_t io;
    bool ready;
    int csq;                    /* signal quality 0..31, 99 unknown */
} sim800_t;

/* AT, echo off, text mode, network registration (home or roaming), signal. Returns SIM_OK or SIM_E_*. */
int sim800_init(sim800_t *m, const sim_io_t *io);
/* Number in international form ("+216..."), text up to 160 GSM characters (cut if longer; characters outside 0x20..0x7E become '?'). */
int sim800_send_sms(sim800_t *m, const char *number, const char *text);

#ifdef __cplusplus
}
#endif
#endif
