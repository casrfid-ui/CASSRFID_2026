/*
 * fwi.h - Fire Weather Index engine for the box (ESP32), C99, no heap, no OS dependency.
 *
 * One call per hour. FFMC moves every hour; DMC and DC move once a day at local noon with the
 * rain of the last 24 hours. The state (codes + 24 h rain history) can be saved to and restored
 * from the board's non-volatile memory through a small storage interface.
 *
 * Reference implementation: ai-data/box/fwi/python (this port is checked against it).
 * Units: temperature degC, relative humidity %, wind km/h, rain mm.
 */
#ifndef FWI_H
#define FWI_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define FWI_RAIN_HOURS 24     /* length of the rain history (hours) */
#define FWI_NOON_HOUR  12     /* local hour at which DMC and DC move */

/* Values used on the very first start, and until real data has filled the 24 h history. */
#define FWI_DEFAULT_FFMC     85.0
#define FWI_DEFAULT_DMC       6.0
#define FWI_DEFAULT_DC       15.0
#define FWI_DEFAULT_RAIN_MM   0.0   /* per hour; 0 = assume dry (safe side: danger is not underestimated) */

#define FWI_ALERT_FROM_CLASS  3     /* class "high" (FWI >= 21.3) and above -> Alert mode */

typedef enum { FWI_MODE_ECO = 0, FWI_MODE_ALERT = 1 } fwi_mode_t;

typedef enum {
    FWI_OK         =  0,
    FWI_ERR_INPUT  = -1,   /* observation out of range or not finite; state left untouched */
    FWI_ERR_ARG    = -2,   /* NULL pointer */
    FWI_ERR_BLOB   = -3    /* saved state unreadable (size, magic, version, CRC or content) */
} fwi_status_t;

typedef enum {
    FWI_START_DEFAULTS = 0,   /* no valid saved state: default values are used */
    FWI_START_RESTORED = 1    /* state and 24 h rain history read back from storage */
} fwi_start_t;

/* Seasonal day-length tables, January to December (46 N, Van Wagner 1987). */
extern const double fwi_le_46n[12];   /* DMC */
extern const double fwi_lf_46n[12];   /* DC  */

/* ---- State -------------------------------------------------------------------------------- */
typedef struct {
    double  ffmc, dmc, dc;
    double  rain_mm[FWI_RAIN_HOURS];  /* ring buffer of hourly rain; starts at the default value  */
    uint8_t head;                     /* next slot to write = oldest value                        */
    uint8_t real_hours;               /* hours of real data recorded, saturates at 24             */
} fwi_state_t;

/* ---- Storage (non-volatile memory) -------------------------------------------------------- */
typedef struct {
    /* Read up to `len` bytes of the saved blob into `buf`. Return the number of bytes read, or < 0. */
    int (*read)(void *ctx, uint8_t *buf, size_t len);
    /* Write the blob. Return 0 on success, < 0 on failure. */
    int (*write)(void *ctx, const uint8_t *buf, size_t len);
    void *ctx;
} fwi_storage_t;

#define FWI_BLOB_SIZE 228   /* 4 magic + 1 version + 1 head + 1 real + 1 pad + 27 * 8 doubles + 4 CRC */

/* ---- Engine ------------------------------------------------------------------------------- */
typedef struct {
    fwi_state_t          state;
    const double        *le;        /* 12-value DMC day-length table */
    const double        *lf;        /* 12-value DC  day-length table */
    const fwi_storage_t *storage;   /* NULL = no persistence         */
} fwi_engine_t;

typedef struct {
    int    hour;        /* local hour 0..23 (from the RTC) */
    int    month;       /* 1..12 (from the RTC)            */
    double temp_c;      /* BME680, compensated             */
    double rh_pct;      /* BME680, compensated             */
    double wind_kmh;    /* simulated in the prototype      */
    double rain_mm;     /* rain over the last hour; simulated in the prototype */
} fwi_input_t;

typedef struct {
    double     ffmc, dmc, dc, isi, bui, fwi;
    uint8_t    danger;          /* 0..5: very low, low, moderate, high, very high, extreme */
    fwi_mode_t mode;
    uint8_t    history_hours;   /* hours of real data behind the 24 h rain history (0..24) */
    uint8_t    provisional;     /* 1 while the history still contains default values       */
    uint8_t    saved;           /* 1 if the state was written to storage this hour         */
} fwi_output_t;

/* Load defaults, then try to restore the saved state. `le`/`lf` may be NULL (46 N tables). */
fwi_start_t fwi_engine_init(fwi_engine_t *e, const fwi_storage_t *storage, const double *le, const double *lf);

/* Advance one hour, update the outputs, save the state. The state is unchanged on error. */
fwi_status_t fwi_engine_update_hour(fwi_engine_t *e, const fwi_input_t *in, fwi_output_t *out);

/* Rain accumulated over the history window (mm). */
double fwi_rain_24h(const fwi_state_t *s);

void         fwi_state_set_defaults(fwi_state_t *s);
fwi_status_t fwi_state_pack(const fwi_state_t *s, uint8_t buf[FWI_BLOB_SIZE]);
fwi_status_t fwi_state_unpack(fwi_state_t *s, const uint8_t *buf, size_t len);

/* ---- The six components as pure functions (same names as the Python reference) ------------- */
double fwi_ffmc_daily(double f0, double temp, double rh, double wind, double rain);
double fwi_ffmc_hourly(double f0, double temp, double rh, double wind, double rain, double hours);
double fwi_dmc(double p0, double temp, double rh, double rain24, int month, const double *le);
double fwi_dc(double d0, double temp, double rain24, int month, const double *lf);
double fwi_isi(double ffmc, double wind);
double fwi_bui(double dmc, double dc);
double fwi_fwi(double isi, double bui);

int         fwi_danger_class(double fwi);   /* EFFIS: 5.2 / 11.2 / 21.3 / 38 / 50 */
fwi_mode_t  fwi_mode_for_class(int danger);

#ifdef __cplusplus
}
#endif
#endif /* FWI_H */
