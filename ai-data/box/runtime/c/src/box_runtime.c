#include <math.h>
#include <string.h>
#include "box_runtime.h"

/* ---- small helpers ------------------------------------------------------------------------------ */
static uint32_t crc32(const uint8_t *p, size_t n)
{
    uint32_t crc = 0xFFFFFFFFu;
    size_t i;
    int b;
    for (i = 0; i < n; i++) {
        crc ^= p[i];
        for (b = 0; b < 8; b++) crc = (crc >> 1) ^ (0xEDB88320u & (uint32_t)-(int32_t)(crc & 1u));
    }
    return ~crc;
}

static void put32(uint8_t *p, uint32_t v) { p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24); }
static uint32_t get32(const uint8_t *p) { return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24); }

/* Seals a blob: the last 4 bytes hold the CRC32 of the rest. */
static void seal(uint8_t *b, size_t n) { put32(b + n - 4, crc32(b, n - 4)); }
static bool sealed_ok(const uint8_t *b, size_t n, const char magic[4])
{
    return memcmp(b, magic, 4) == 0 && get32(b + n - 4) == crc32(b, n - 4);
}

/* Civil date from days since 1970-01-01 (Hinnant). Only the month is needed. */
static int month_of_days(int64_t z)
{
    int64_t era, doe, yoe, doy, mp;
    z += 719468;
    era = (z >= 0 ? z : z - 146096) / 146097;
    doe = z - era * 146097;
    yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    mp = (5 * doy + 2) / 153;
    return (int)(mp < 10 ? mp + 3 : mp - 9);
}

static int64_t floor_div(int64_t a, int64_t b) { int64_t q = a / b; return (a % b != 0 && (a < 0) != (b < 0)) ? q - 1 : q; }

/* ---- flash copies ------------------------------------------------------------------------------- */
#define GAS_BLOB (4 + 1 + 3 + 8 * GC_NSTEP + 4)     /* magic, version, pad, baseline, crc */
#define SM_BLOB  (4 + 1 + 1 + 1 + 1 + 2 + 2 + 8 + 4)/* magic, version, state, gasp, reasons, clear_count, pad, hold, crc */
#define META_BLOB (4 + 4 + 8 + 4)

static int kv_write(box_runtime_t *rt, const char *key, const uint8_t *b, size_t n)
{
    if (!rt->kv.write) return 0;                    /* persistence disabled: nothing to fail */
    return rt->kv.write(rt->kv.ctx, key, b, n) == 0 ? 0 : -1;
}

static int fwi_read(void *ctx, uint8_t *buf, size_t len)
{
    box_runtime_t *rt = ctx;
    return rt->kv.read ? rt->kv.read(rt->kv.ctx, BOX_KEY_FWI, buf, len) : -1;
}
static int fwi_write(void *ctx, const uint8_t *buf, size_t len)
{
    box_runtime_t *rt = ctx;
    return rt->kv.write ? rt->kv.write(rt->kv.ctx, BOX_KEY_FWI, buf, len) : -1;
}

static int save_baseline(box_runtime_t *rt)
{
    uint8_t b[GAS_BLOB];
    double base[GC_NSTEP];
    if (!gc_snapshot(&rt->gas, base)) return 0;
    memset(b, 0, sizeof b);
    memcpy(b, "BGB1", 4);
    b[4] = 1;
    memcpy(b + 8, base, sizeof base);
    seal(b, sizeof b);
    return kv_write(rt, BOX_KEY_GAS, b, sizeof b);
}

static bool load_baseline(box_runtime_t *rt)
{
    uint8_t b[GAS_BLOB];
    double base[GC_NSTEP];
    int i;
    if (!rt->kv.read || rt->kv.read(rt->kv.ctx, BOX_KEY_GAS, b, sizeof b) != (int)sizeof b) return false;
    if (!sealed_ok(b, sizeof b, "BGB1") || b[4] != 1) return false;
    memcpy(base, b + 8, sizeof base);
    for (i = 0; i < GC_NSTEP; i++) if (!isfinite(base[i]) || base[i] < -5.0 || base[i] > 30.0) return false;   /* ln of 1 kohm .. 120 Mohm */
    gc_restore(&rt->gas, base);
    return true;
}

static int save_sm(box_runtime_t *rt)
{
    uint8_t b[SM_BLOB];
    memset(b, 0, sizeof b);
    memcpy(b, "BSM1", 4);
    b[4] = 1;
    b[5] = rt->sm.state;
    b[6] = rt->sm.last_gasp_sent;
    b[7] = rt->sm.reasons;
    b[8] = (uint8_t)rt->sm.clear_count; b[9] = (uint8_t)(rt->sm.clear_count >> 8);
    memcpy(b + 12, &rt->sm.fire_clear_s, 8);
    seal(b, sizeof b);
    return kv_write(rt, BOX_KEY_SM, b, sizeof b);
}

static bool load_sm(box_runtime_t *rt)
{
    uint8_t b[SM_BLOB];
    double hold;
    if (!rt->kv.read || rt->kv.read(rt->kv.ctx, BOX_KEY_SM, b, sizeof b) != (int)sizeof b) return false;
    if (!sealed_ok(b, sizeof b, "BSM1") || b[4] != 1 || b[5] > SM_FIRE) return false;
    memcpy(&hold, b + 12, 8);
    if (!isfinite(hold) || hold < 0.0) return false;
    rt->sm.state = b[5];
    rt->sm.last_gasp_sent = b[6] != 0;
    rt->sm.reasons = b[7];
    rt->sm.clear_count = b[8] | (b[9] << 8);
    rt->sm.fire_clear_s = hold;
    rt->saved_sm_state = rt->sm.state;
    rt->saved_gasp = rt->sm.last_gasp_sent;
    return true;
}

static int save_meta(box_runtime_t *rt)
{
    uint8_t b[META_BLOB];
    memset(b, 0, sizeof b);
    memcpy(b, "BMT1", 4);
    memcpy(b + 8, &rt->last_fwi_hour, 8);
    seal(b, sizeof b);
    return kv_write(rt, BOX_KEY_META, b, sizeof b);
}

static bool load_meta(box_runtime_t *rt)
{
    uint8_t b[META_BLOB];
    if (!rt->kv.read || rt->kv.read(rt->kv.ctx, BOX_KEY_META, b, sizeof b) != (int)sizeof b) return false;
    if (!sealed_ok(b, sizeof b, "BMT1")) return false;
    memcpy(&rt->last_fwi_hour, b + 8, 8);
    rt->have_fwi_hour = true;
    return true;
}

/* ---- public API --------------------------------------------------------------------------------- */
void box_config_default(box_config_t *cfg)
{
    memset(cfg, 0, sizeof *cfg);
    cfg->utc_offset_s = 0;
    cfg->baseline_save_period_s = 3600.0;
    gc_config_default(&cfg->gas);
    sm_config_default(&cfg->sm);
    fl_config_default(&cfg->flame);
}

int box_runtime_init(box_runtime_t *rt, const box_config_t *cfg, const box_kv_t *kv)
{
    box_config_t d;
    int mask = 0;
    if (!rt) return -1;
    memset(rt, 0, sizeof *rt);
    if (!cfg) { box_config_default(&d); cfg = &d; }
    rt->cfg = *cfg;
    if (kv) rt->kv = *kv;
    if (gc_init(&rt->gas, &rt->cfg.gas) != 0) return -1;
    if (!(rt->cfg.baseline_save_period_s > 0.0)) return -1;
    sm_init(&rt->sm, &rt->cfg.sm);

    rt->fwi_store.read = fwi_read;
    rt->fwi_store.write = fwi_write;
    rt->fwi_store.ctx = rt;
    if (fwi_engine_init(&rt->fwi, kv ? &rt->fwi_store : NULL, NULL, NULL) == FWI_START_RESTORED) mask |= BOX_RESTORED_FWI;
    if (load_baseline(rt)) mask |= BOX_RESTORED_GAS;
    if (load_sm(rt)) mask |= BOX_RESTORED_SM;
    if (load_meta(rt)) mask |= BOX_RESTORED_META;
    rt->fwi_last.mode = FWI_MODE_ECO;
    rt->fwi_last.provisional = 1;
    rt->gas_last.warmup = true;
    return mask;
}

void box_runtime_reset_fire(box_runtime_t *rt)
{
    sm_reset(&rt->sm);
    rt->saved_sm_state = rt->sm.state;
    save_sm(rt);
}

/* FWI values from the current state and wind, without advancing the hour (hour already applied before a reboot). */
static void fwi_peek(box_runtime_t *rt, double wind_kmh)
{
    const fwi_state_t *s = &rt->fwi.state;
    fwi_output_t *o = &rt->fwi_last;
    o->ffmc = s->ffmc; o->dmc = s->dmc; o->dc = s->dc;
    o->isi = fwi_isi(s->ffmc, wind_kmh);
    o->bui = fwi_bui(s->dmc, s->dc);
    o->fwi = fwi_fwi(o->isi, o->bui);
    o->danger = (uint8_t)fwi_danger_class(o->fwi);
    o->mode = fwi_mode_for_class(o->danger);
    o->history_hours = s->real_hours;
    o->provisional = s->real_hours < FWI_RAIN_HOURS;
    o->saved = 0;
}

int box_runtime_step(box_runtime_t *rt, const box_tick_t *t, box_output_t *out)
{
    box_output_t o;
    sm_inputs_t x;
    double dt = 0.0;
    int64_t local_s, hour_idx;
    bool gas_smoke, gas_fault, flame;

    if (!rt || !t || !out || t->unix_s < 0) return -1;
    memset(&o, 0, sizeof o);

    if (rt->have_last_unix) {
        if (t->unix_s < rt->last_unix_s) o.clock_jump = true;
        else dt = (double)(t->unix_s - rt->last_unix_s);
    }
    rt->last_unix_s = t->unix_s;
    rt->have_last_unix = true;

    /* ---- FWI: one update per local hour, with the rain gathered since the previous one ---- */
    if (t->rain_mm > 0.0 && isfinite(t->rain_mm)) rt->rain_acc_mm += t->rain_mm;
    local_s = t->unix_s + rt->cfg.utc_offset_s;
    hour_idx = floor_div(local_s, 3600);
    o.fwi_status = FWI_OK;
    if (t->weather_valid) {
        if (!rt->have_fwi_hour || hour_idx != rt->last_fwi_hour) {
            fwi_input_t in;
            in.hour = (int)(hour_idx - floor_div(hour_idx, 24) * 24);
            in.month = month_of_days(floor_div(local_s, 86400));
            in.temp_c = t->temp_c; in.rh_pct = t->rh_pct; in.wind_kmh = t->wind_kmh; in.rain_mm = rt->rain_acc_mm;
            o.fwi_status = fwi_engine_update_hour(&rt->fwi, &in, &rt->fwi_last);
            if (o.fwi_status == FWI_OK) {
                o.fwi_updated = true;
                rt->rain_acc_mm = 0.0;
                rt->last_fwi_hour = hour_idx;
                rt->have_fwi_hour = true;
                rt->have_fwi_out = true;
                if (save_meta(rt) != 0) o.storage_errors++;
                if (rt->kv.write && !rt->fwi_last.saved) o.storage_errors++;
            }
        } else if (!rt->have_fwi_out) {
            fwi_peek(rt, t->wind_kmh);          /* first wake-up after a reboot inside an hour already applied */
            rt->have_fwi_out = true;
        }
    }
    o.fwi = rt->fwi_last;

    /* ---- gas chain: a scan is used only when the battery allows it ---- */
    o.want_gas_scan = !t->battery_low;
    if (t->gas_valid && !t->battery_low) {
        double dtg = rt->have_last_gas ? (double)(t->unix_s - rt->last_gas_unix_s) : 30.0;
        if (!(dtg >= 1.0)) dtg = 1.0;
        if (gc_update(&rt->gas, t->gas_ohm, t->gas_temp_c, t->gas_rh_pct, dtg, &rt->gas_last) == 0) {
            o.gas_scanned = true;
            rt->last_gas_unix_s = t->unix_s;
            rt->have_last_gas = true;
            if (!rt->gas_last.warmup && !rt->gas_last.scan_bad && rt->gas_last.cls == GC_NORMAL) {
                if (!rt->baseline_saved_once
                    || (double)(t->unix_s - rt->last_baseline_save_s) >= rt->cfg.baseline_save_period_s) {
                    if (save_baseline(rt) == 0) {
                        o.baseline_saved = true;
                        rt->baseline_saved_once = true;
                        rt->last_baseline_save_s = t->unix_s;
                    } else {
                        o.storage_errors++;
                    }
                }
            }
        }
    }
    o.gas = rt->gas_last;
    gas_smoke = !t->battery_low && rt->gas_last.cls == GC_SMOKE;
    gas_fault = rt->gas_last.cls == GC_FAULT;

    /* ---- state machine ---- */
    sm_inputs_default(&x);
    x.gas_smoke = gas_smoke;
    x.gas_fault = gas_fault;
    flame = t->flame;
    if (t->flame_n > 0) {
        if (fl_process(t->flame_raw, t->flame_n, &rt->cfg.flame, &o.flame) == 0) {
            o.flame_processed = true;
            flame = o.flame.detected;
        } else {
            o.flame_status = -1;                  /* refused burst: fall back to the plain flag */
        }
    }
    x.flame = flame;
    x.camera_valid = t->camera_valid;
    x.camera_label = t->camera_label;
    x.camera_conf = t->camera_conf;
    x.fwi_mode = (uint8_t)(rt->fwi_last.mode == FWI_MODE_ALERT ? SM_FWI_ALERT : SM_FWI_ECO);
    x.fwi_danger = rt->fwi_last.danger;
    x.battery_low = t->battery_low;
    x.housing_hot = t->housing_hot;
    x.supply_fault = t->supply_fault;
    x.dt_s = dt;
    if (sm_step(&rt->sm, &x, &o.sm) != 0) return -1;

    if (rt->sm.state != rt->saved_sm_state || rt->sm.last_gasp_sent != rt->saved_gasp) {
        if (save_sm(rt) == 0) { rt->saved_sm_state = rt->sm.state; rt->saved_gasp = rt->sm.last_gasp_sent; }
        else o.storage_errors++;
    }
    *out = o;
    return 0;
}
