#include <math.h>
#include <string.h>
#include "state_machine.h"

void sm_config_default(sm_config_t *c)
{
    c->eco_interval_s = 300.0;
    c->alert_interval_s = 30.0;
    c->survival_interval_s = 3600.0;
    c->suspicion_interval_s = 30.0;
    c->flame_reads_to_trigger = 2;
    c->clear_scans = 10;
    c->camera_confidence = 0.6;
    c->camera_min_period_s = 30.0;
    c->alert_repeats = 3;
    c->fire_hold_clear_s = 1800.0;
    c->heartbeat_s = 600.0;
    c->pump_danger_from = 3;
    c->flame_recheck_s = 30.0;
}

void sm_inputs_default(sm_inputs_t *x)
{
    memset(x, 0, sizeof *x);
    x->fwi_mode = SM_FWI_ECO;
    x->dt_s = 30.0;
}

void sm_init(sm_machine_t *m, const sm_config_t *cfg)
{
    memset(m, 0, sizeof *m);
    if (cfg) m->cfg = *cfg; else sm_config_default(&m->cfg);
    m->state = SM_NORMAL;
    m->since_camera_s = m->cfg.camera_min_period_s;
}

void sm_reset(sm_machine_t *m)
{
    m->state = SM_NORMAL;
    m->clear_count = 0;
    m->fire_clear_s = 0.0;
    m->reasons = 0;
}

static void add_frame(sm_output_t *o, uint8_t kind, uint8_t repeats)
{
    if (o->n_frames < SM_MAX_FRAMES) {
        o->frames[o->n_frames].kind = kind;
        o->frames[o->n_frames].repeats = repeats;
        o->n_frames++;
    }
}

int sm_step(sm_machine_t *m, const sm_inputs_t *x, sm_output_t *out)
{
    const sm_config_t *c;
    sm_output_t o;
    uint8_t previous, trig = 0;
    bool confirm, awake, pump;

    if (!m || !x || !out || !(x->dt_s >= 0.0) || !isfinite(x->dt_s)) return -1;
    c = &m->cfg;
    memset(&o, 0, sizeof o);

    m->survival = x->battery_low;
    m->flame_reads = x->flame ? m->flame_reads + 1 : 0;
    m->since_frame_s += x->dt_s;
    m->since_camera_s += x->dt_s;
    previous = m->state;

    if (x->gas_smoke) trig |= SM_R_GAS;
    if (m->flame_reads >= c->flame_reads_to_trigger) trig |= SM_R_FLAME;
    confirm = x->camera_valid && (x->camera_label == SM_CAM_FIRE || x->camera_label == SM_CAM_SMOKE)
              && x->camera_conf >= c->camera_confidence;
    if (confirm) trig |= SM_R_CAMERA;
    /* Survival: gas scans are suspended, only the flame sensor (hardware wake) can start a suspicion */
    if (x->battery_low) trig &= (uint8_t)(SM_R_FLAME | SM_R_CAMERA);

    if (m->state == SM_NORMAL) {
        if (trig & (SM_R_GAS | SM_R_FLAME)) { m->state = SM_SUSPICION; m->clear_count = 0; }
    } else if (m->state == SM_SUSPICION) {
        if (confirm || ((trig & SM_R_GAS) && (trig & SM_R_FLAME))) {
            m->state = SM_FIRE;
            add_frame(&o, SM_FRAME_ALERT, (uint8_t)c->alert_repeats);
        } else if (trig & (SM_R_GAS | SM_R_FLAME)) {
            m->clear_count = 0;
        } else {
            m->clear_count++;
            if (m->clear_count >= c->clear_scans) m->state = SM_NORMAL;
        }
    } else if (m->state == SM_FIRE) {
        if (trig) {
            m->fire_clear_s = 0.0;
        } else {
            m->fire_clear_s += x->dt_s;
            if (m->fire_clear_s >= c->fire_hold_clear_s) { m->state = SM_NORMAL; m->fire_clear_s = 0.0; }
        }
    }

    if (m->state != previous && m->state != SM_FIRE) add_frame(&o, SM_FRAME_STATE_CHANGE, 1);
    if (m->state == SM_FIRE && previous == SM_FIRE && confirm) add_frame(&o, SM_FRAME_ALERT, 1);   /* new confirmation inside Fire */
    if (o.n_frames == 0 && m->since_frame_s >= c->heartbeat_s) add_frame(&o, SM_FRAME_HEARTBEAT, 1);
    if (o.n_frames > 0) m->since_frame_s = 0.0;

    m->reasons = (m->state != SM_NORMAL) ? trig : 0;
    if (m->state != SM_NORMAL && x->fwi_danger >= c->pump_danger_from) m->reasons |= SM_R_FWI;

    if ((x->housing_hot || x->supply_fault) && !m->last_gasp_sent) {
        o.last_gasp = true;
        m->last_gasp_sent = true;
        add_frame(&o, SM_FRAME_LAST_GASP, (uint8_t)c->alert_repeats);
    }

    awake = m->state != SM_NORMAL;
    o.camera_on = awake && !x->battery_low && m->since_camera_s >= c->camera_min_period_s;
    if (o.camera_on) m->since_camera_s = 0.0;
    if (awake) o.interval_s = c->suspicion_interval_s;
    else if (x->battery_low) o.interval_s = c->survival_interval_s;
    else o.interval_s = (x->fwi_mode == SM_FWI_ALERT) ? c->alert_interval_s : c->eco_interval_s;
    if (!awake && c->flame_recheck_s > 0.0 && m->flame_reads > 0 && m->flame_reads < c->flame_reads_to_trigger
        && c->flame_recheck_s < o.interval_s)
        o.interval_s = c->flame_recheck_s;            /* a first flame read is confirmed (or not) quickly */
    pump = m->state == SM_FIRE || (m->state == SM_SUSPICION && x->fwi_danger >= c->pump_danger_from);
    o.state = m->state;
    o.gps_on = awake;
    o.actuator = pump;
    o.reasons = m->reasons;
    *out = o;
    return 0;
}
