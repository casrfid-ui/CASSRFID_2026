/* Request headers and strict parse of the gateway answer (JSON, version 1). */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "box_camera.h"

int cam_build_headers(char *buf, size_t cap, const cam_ids_t *ids)
{
    int n = snprintf(buf, cap, "X-Box-Id: %u\r\nX-Req-Id: %lu\r\nX-Time: %lld\r\nX-Reasons: %u\r\nContent-Type: image/jpeg\r\n",
                     (unsigned)ids->box_id, (unsigned long)ids->req_id, (long long)ids->unix_s, (unsigned)ids->reasons);
    return (n < 0 || (size_t)n >= cap) ? -1 : n;
}

/* Pointer to the value after  "key" : , or NULL. The key is looked up as a quoted token. */
static const char *find_value(const char *s, const char *key)
{
    char pat[24];
    const char *p;
    size_t k = strlen(key);
    if (k + 3 > sizeof pat) return NULL;
    pat[0] = '"'; memcpy(pat + 1, key, k); pat[k + 1] = '"'; pat[k + 2] = '\0';
    p = strstr(s, pat);
    if (!p) return NULL;
    p += k + 2;
    while (*p == ' ' || *p == '\t') p++;
    if (*p != ':') return NULL;
    p++;
    while (*p == ' ' || *p == '\t') p++;
    return p;
}

static int parse_uint(const char *p, unsigned long *v)
{
    char *end;
    if (*p < '0' || *p > '9') return -1;
    *v = strtoul(p, &end, 10);
    return (*end == ',' || *end == '}' || *end == ' ' || *end == '\0') ? 0 : -1;
}

int cam_parse_response(const char *body, uint32_t expect_id, uint8_t *label, double *conf, int *model_ms)
{
    const char *p;
    unsigned long v, id;
    char name[16];
    size_t i = 0;
    double c;
    char *end;

    if (!body || !label || !conf || !model_ms) return -1;
    *model_ms = -1;
    p = find_value(body, "v");
    if (!p || parse_uint(p, &v) != 0 || v != 1) return -1;
    p = find_value(body, "id");
    if (!p || parse_uint(p, &id) != 0) return -1;
    if (id != (unsigned long)expect_id) return -2;
    if (find_value(body, "error")) return -3;
    p = find_value(body, "label");
    if (!p || *p != '"') return -1;
    for (p++; *p && *p != '"' && i < sizeof name - 1; p++) name[i++] = *p;
    if (*p != '"') return -1;
    name[i] = '\0';
    p = find_value(body, "conf");
    if (!p || !((*p >= '0' && *p <= '9') || *p == '.')) return -1;
    c = strtod(p, &end);
    if (end == p || !(c >= 0.0 && c <= 1.0)) return -1;
    if (!strcmp(name, "fire")) *label = CAM_LABEL_FIRE;
    else if (!strcmp(name, "smoke")) *label = CAM_LABEL_SMOKE;
    else if (!strcmp(name, "background")) *label = CAM_LABEL_BACKGROUND;
    else return -1;
    *conf = c;
    p = find_value(body, "ms");
    if (p && parse_uint(p, &v) == 0 && v < 1000000UL) *model_ms = (int)v;
    return 0;
}
