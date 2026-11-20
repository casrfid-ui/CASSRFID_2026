/* Box camera: image quality check, session (power, capture, Wi-Fi, send to the gateway, parse) and protocol.
 * C99, no heap, no OS call. The hardware is reached only through cam_hw_t (mocked in the tests).
 * The CNN is not here: the gateway classifies the JPEG (../../gateway/vision). */
#ifndef BOX_CAMERA_H
#define BOX_CAMERA_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define CAM_LUMA_MAX 19200               /* largest grayscale frame for the quality check (160 x 120) */
#define CAM_RESP_MAX 256                 /* largest gateway answer kept (bytes, with the final NUL) */
#define CAM_HEADERS_MAX 192

/* Labels: same numbers as SM_CAM_* in state_machine.h */
enum { CAM_LABEL_BACKGROUND = 0, CAM_LABEL_FIRE = 1, CAM_LABEL_SMOKE = 2 };

/* Quality flags */
enum { CAM_Q_DARK = 1, CAM_Q_BLOCKED = 2, CAM_Q_SATURATED = 4, CAM_Q_BLURRY = 8 };

/* Session status */
enum {
    CAM_OK = 0,
    CAM_E_ARG = 1,        /* bad arguments or hooks missing */
    CAM_E_POWER = 2,      /* camera did not power on */
    CAM_E_CAPTURE = 3,    /* grayscale or JPEG capture failed */
    CAM_E_QUALITY = 4,    /* image refused: see quality.flags */
    CAM_E_WIFI = 5,       /* no Wi-Fi link */
    CAM_E_TIMEOUT = 6,    /* session budget used up */
    CAM_E_HTTP = 7,       /* gateway unreachable, or answered with an error status */
    CAM_E_RESPONSE = 8    /* answer malformed, stale, unknown label or confidence out of range */
};

typedef struct {
    double min_mean;          /* DARK below */
    double min_std;           /* BLOCKED below */
    double max_sat_frac;      /* SATURATED above (share of pixels >= 250) */
    double min_grad;          /* BLURRY below (only when not BLOCKED) */
    int warmup_frames;
    uint32_t frame_period_ms; /* wait between warm-up frames */
    uint32_t wifi_timeout_ms;
    uint32_t post_timeout_ms;
    uint32_t retry_delay_ms;
    int max_attempts;
    uint32_t session_budget_ms;
    bool upload_even_if_poor;
} cam_config_t;

typedef struct {
    double mean, std, sat_frac, dark_frac, grad;
    uint8_t flags;            /* CAM_Q_* */
} cam_quality_t;

typedef struct {
    uint8_t box_id;
    uint32_t req_id;          /* increases at every session; the answer must carry the same id */
    int64_t unix_s;
    uint8_t reasons;          /* state machine reason bits */
} cam_ids_t;

typedef struct {
    cam_ids_t ids;
    const uint8_t *jpeg;
    size_t jpeg_len;
    char headers[CAM_HEADERS_MAX];   /* ready-made request headers ("Name: value\r\n" lines) */
} cam_request_t;

typedef struct {
    uint8_t status;           /* CAM_* */
    bool valid;               /* label and conf usable (status == CAM_OK) */
    uint8_t label;            /* CAM_LABEL_* */
    double conf;              /* 0..1 */
    cam_quality_t quality;
    int attempts;             /* uploads tried */
    uint32_t elapsed_ms;
    int http_status;          /* last HTTP status, 0 if none */
    int model_ms;             /* inference time reported by the gateway, -1 if absent */
} cam_result_t;

/* Hardware hooks supplied by the firmware (or by a mock). Every hook returns 0 on success, < 0 on failure. */
typedef struct {
    void *ctx;
    int (*power)(void *ctx, bool on);
    /* small grayscale frame, row-major; set *w and *h; buf holds `cap` bytes */
    int (*grab_luma)(void *ctx, uint8_t *buf, size_t cap, int *w, int *h);
    int (*grab_jpeg)(void *ctx, uint8_t *buf, size_t cap, size_t *len);
    int (*wifi)(void *ctx, bool on, uint32_t timeout_ms);
    /* POST the request; write the NUL-terminated body of the answer to resp (resp_cap bytes) and the HTTP status */
    int (*post)(void *ctx, const cam_request_t *rq, char *resp, size_t resp_cap, uint32_t timeout_ms, int *http_status);
    uint32_t (*now_ms)(void *ctx);
    void (*delay_ms)(void *ctx, uint32_t ms);
} cam_hw_t;

typedef struct {
    uint8_t luma[CAM_LUMA_MAX];
    char resp[CAM_RESP_MAX];
} cam_workspace_t;

void cam_config_default(cam_config_t *cfg);

/* Quality of a grayscale frame (w * h <= CAM_LUMA_MAX). Returns 0, or -1 for bad arguments. */
int cam_quality(const uint8_t *luma, int w, int h, const cam_config_t *cfg, cam_quality_t *out);

/* "X-Box-Id: ..\r\nX-Req-Id: ..\r\nX-Time: ..\r\nX-Reasons: ..\r\nContent-Type: image/jpeg\r\n".
 * Returns the length, or -1 if cap is too small. */
int cam_build_headers(char *buf, size_t cap, const cam_ids_t *ids);

/* Strict parse of the gateway answer (NUL-terminated). Returns 0, or
 * -1 malformed (not v1, missing or bad field, unknown label, conf outside 0..1),
 * -2 id differs from expect_id, -3 the gateway reported an error. model_ms is -1 when absent. */
int cam_parse_response(const char *body, uint32_t expect_id, uint8_t *label, double *conf, int *model_ms);

/* The whole session. Always powers the camera and Wi-Fi off before returning, whatever happens.
 * jpeg/jpeg_cap: buffer for the JPEG (the firmware sizes it, e.g. 60 kB). Returns 0 and fills *out (also on a
 * session failure: see out->status), or -1 for bad arguments (then out->status == CAM_E_ARG). */
int cam_session_run(const cam_hw_t *hw, const cam_config_t *cfg, const cam_ids_t *ids, cam_workspace_t *ws,
                    uint8_t *jpeg, size_t jpeg_cap, cam_result_t *out);

#ifdef __cplusplus
}
#endif
#endif
