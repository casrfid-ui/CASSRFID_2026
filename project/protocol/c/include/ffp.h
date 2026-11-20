/* FFP: the 16-byte LoRa frame shared by the boxes and the gateway bridge. C99, no heap, no I/O.
 * Layout and meaning of every field: ../../PROTOCOL.md. Python mirror: ../../python/ffp (checked by test vectors). */
#ifndef FFP_H
#define FFP_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define FFP_FRAME_LEN 16
#define FFP_PAYLOAD_LEN 12

/* Frame types. 1..4 are the same numbers as SM_FRAME_* of the box state machine. */
enum {
    FFP_T_ALERT = 1, FFP_T_STATE = 2, FFP_T_HEARTBEAT = 3, FFP_T_LAST_GASP = 4,
    FFP_T_TELEM = 5, FFP_T_POS = 6,
    FFP_T_ACK = 8, FFP_T_CMD = 9, FFP_T_TIME = 10
};

/* Header flags (low nibble of byte 0) */
enum { FFP_F_SIM_WX = 1, FFP_F_RELAYED = 2, FFP_F_ACK_REQ = 4, FFP_F_PRIORITY = 8 };

/* Node ids (4 bits). 0 = "any gateway" as a destination. */
enum { FFP_ID_ANY_GW = 0, FFP_ID_BOX_MIN = 1, FFP_ID_BOX_MAX = 7, FFP_ID_GW_MIN = 8, FFP_ID_GW_MAX = 11, FFP_ID_BROADCAST = 15 };

/* Status flags (STATUS payload byte p5) */
enum {
    FFP_SF_BATTERY_LOW = 1, FFP_SF_HOUSING_HOT = 2, FFP_SF_SUPPLY_FAULT = 4, FFP_SF_CLOCK_UNSYNCED = 8,
    FFP_SF_STORAGE_ERROR = 16, FFP_SF_GPS_ON = 32, FFP_SF_PUMP = 64, FFP_SF_CAMERA_ON = 128
};

/* Box mode as sent (STATUS) */
enum { FFP_MODE_ECO = 0, FFP_MODE_ALERT = 1, FFP_MODE_SURVIVAL = 2 };

/* Commands (CMD payload byte p0) */
enum {
    FFP_C_SET_THRESH = 1,   /* a0 smoke_on x100, a1 smoke_off x100, a2 camera confidence x100 */
    FFP_C_RISK_PRIOR = 2,   /* a0 prior x255, a1 level (0 low, 1 moderate, 2 high), a2 ttl in 10 min units */
    FFP_C_FORCE_MODE = 3,   /* a0 0 none / 1 eco / 2 alert, a1 ttl in 10 min units */
    FFP_C_RESET_FIRE = 4,
    FFP_C_SIM_WX = 5,       /* a0 wind km/h, a1 rain mm/h x10, a2 ttl in 10 min units (0 = back to the generator) */
    FFP_C_SET_SF = 6,       /* a0 spreading factor 7..12 */
    FFP_C_PING = 7
};

/* ACK flags (ACK payload byte p2) */
enum { FFP_AF_OPERATOR = 1, FFP_AF_SBC_UP = 2, FFP_AF_FROM_BRIDGE = 4 };

typedef struct {
    uint8_t type, flags, origin, dest, seq;
    uint8_t payload[FFP_PAYLOAD_LEN];
} ffp_frame_t;

/* STATUS: ALERT, STATE, HEARTBEAT and LAST_GASP share this payload. All fields are the wire integers. */
typedef struct {
    uint8_t state;          /* 0 normal, 1 suspicion, 2 fire (SM_*) */
    uint8_t mode;           /* FFP_MODE_* */
    uint8_t reasons;        /* SM_R_* bits: gas 1, flame 2, camera 4, fwi 8 */
    uint8_t gas_score;      /* round(255 * score) */
    uint8_t gas_class;      /* GC_*: 0 normal, 1 smoke, 2 decoy, 3 fault */
    uint8_t gas_faults;     /* GC_F_* (3 bits) */
    uint8_t warmup, flame, scan_bad;       /* 0 / 1 */
    uint8_t cam_label;      /* 0 background, 1 fire, 2 smoke */
    uint8_t cam_valid;      /* 0 / 1 */
    uint8_t cam_status;     /* CAM_* (0..8) */
    uint8_t cam_conf;       /* round(255 * conf) */
    uint8_t flags;          /* FFP_SF_* */
    uint8_t fwi_x2;         /* round(2 * FWI), saturated */
    uint8_t danger;         /* 0..5 */
    uint8_t fwi_updated, provisional;      /* 0 / 1 */
    uint8_t repeat;         /* 0..3: index of this copy among the repeated sends */
    uint8_t battery_pct;
    uint8_t band[3];        /* gas depth per band, round(64 * ln units), saturated */
} ffp_status_t;

/* TELEM: weather and FWI codes, sent after each FWI hour. */
typedef struct {
    int16_t temp_c100;      /* 0.01 degC */
    uint8_t rh_x2;          /* 0.5 % */
    uint8_t wind_kmh;       /* saturated at 255 */
    uint8_t rain_x10;       /* mm over the last hour x10, saturated */
    uint8_t ffmc_x2_5;      /* round(2.5 * FFMC) */
    uint8_t dmc;            /* round(DMC), saturated */
    uint16_t dc;            /* round(DC), saturated */
    uint8_t isi_x5;         /* round(5 * ISI), saturated */
    uint8_t bui;            /* round(BUI), saturated */
    uint8_t history_hours;  /* 0..24 */
    uint8_t provisional;    /* 0 / 1 */
} ffp_telem_t;

typedef struct {
    int32_t lat_e7, lon_e7;
    int16_t alt_m;
    uint8_t sats;
    uint8_t fix;            /* 0 none, 1 gps */
} ffp_pos_t;

typedef struct {
    uint8_t acked_seq, acked_type, flags;
    int8_t rssi_dbm;        /* as heard by the receiver of the acked frame (clamped to -128..0) */
    int8_t snr_x4;          /* SNR x4 dB */
    uint8_t gw_id;
    uint8_t alert_level;    /* highest active level 0..5 at the gateway */
} ffp_ack_t;

typedef struct { uint8_t id; uint8_t arg[6]; } ffp_cmd_t;
typedef struct { uint32_t unix_s; int8_t utc_offset_q; /* quarter hours */ } ffp_time_t;

uint8_t ffp_crc8(const uint8_t *data, size_t len);                    /* poly 0x07, init 0, no reflection */

/* Returns 0, or -1 (NULL, bad type, id out of range, payload does not fit). */
int ffp_encode(const ffp_frame_t *f, uint8_t out[FFP_FRAME_LEN]);
/* Returns 0, or -1 length != 16 / NULL, -2 CRC, -3 unknown type, -4 invalid ids (origin 0, or 8..15 for box frames). */
int ffp_decode(const uint8_t *in, size_t len, ffp_frame_t *f);

void ffp_frame_init(ffp_frame_t *f, uint8_t type, uint8_t flags, uint8_t origin, uint8_t dest, uint8_t seq);

void ffp_pack_status(ffp_frame_t *f, const ffp_status_t *s);
void ffp_unpack_status(const ffp_frame_t *f, ffp_status_t *s);
void ffp_pack_telem(ffp_frame_t *f, const ffp_telem_t *t);
void ffp_unpack_telem(const ffp_frame_t *f, ffp_telem_t *t);
void ffp_pack_pos(ffp_frame_t *f, const ffp_pos_t *p);
void ffp_unpack_pos(const ffp_frame_t *f, ffp_pos_t *p);
void ffp_pack_ack(ffp_frame_t *f, const ffp_ack_t *a);
void ffp_unpack_ack(const ffp_frame_t *f, ffp_ack_t *a);
void ffp_pack_cmd(ffp_frame_t *f, const ffp_cmd_t *c);
void ffp_unpack_cmd(const ffp_frame_t *f, ffp_cmd_t *c);
void ffp_pack_time(ffp_frame_t *f, const ffp_time_t *t);
void ffp_unpack_time(const ffp_frame_t *f, ffp_time_t *t);

/* Helpers: double <-> wire integer, saturating, NaN -> 0. */
uint8_t ffp_q8(double x, double scale);     /* round(x * scale) clamped to 0..255 */
uint16_t ffp_q16(double x, double scale);

#ifdef __cplusplus
}
#endif
#endif
