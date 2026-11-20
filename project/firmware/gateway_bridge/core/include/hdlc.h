/* Byte framing of the UART between the gateway ESP32 and the SBC: 0x7E | type | payload | crc16 | 0x7E, with 0x7D escaping.
 * CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF) over type + payload. C99, no heap. Python mirror: project/gateway/.../uart_link.py */
#ifndef HDLC_H
#define HDLC_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define HDLC_MAX_PAYLOAD 120

/* Messages bridge -> SBC */
enum { BR_RX_FRAME = 0x01, BR_STATUS = 0x02, BR_SMS_RESULT = 0x03, BR_EMERGENCY = 0x04 };
/* Messages SBC -> bridge */
enum {
    SB_HELLO = 0x80, SB_TX_FRAME = 0x81, SB_SEND_SMS = 0x82, SB_DISPATCHED = 0x83, SB_BYE = 0x84,
    SB_SET_NUMBERS = 0x85, SB_SET_LEVEL = 0x86, SB_SET_TIME = 0x87, SB_PING = 0x88
};

typedef struct {
    uint8_t type;
    uint8_t len;
    uint8_t data[HDLC_MAX_PAYLOAD];
} hdlc_msg_t;

typedef struct {
    uint8_t buf[HDLC_MAX_PAYLOAD + 4];
    size_t n;
    int in_frame, escape;
    uint32_t bad_crc, overflow;
} hdlc_decoder_t;

uint16_t hdlc_crc16(const uint8_t *d, size_t n);
/* Returns the encoded length, or -1 if cap is too small or len too large. */
int hdlc_encode(uint8_t type, const uint8_t *payload, size_t len, uint8_t *out, size_t cap);
void hdlc_decoder_init(hdlc_decoder_t *d);
/* Feed one byte. Returns 1 when a message is complete (in *m), 0 otherwise. */
int hdlc_feed(hdlc_decoder_t *d, uint8_t byte, hdlc_msg_t *m);

#ifdef __cplusplus
}
#endif
#endif
