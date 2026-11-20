import json
from ffn_gateway import uart_link as U
from ffn_gateway.ffp import frame as F

T0 = 1_793_800_000.0


def feed(gw, frame, now, rssi=-90, snr=40):
    gw.handle(U.RxFrame(rssi, snr, frame.encode()), now)


def status(**kw):
    return F.Status(**kw)


def mk(box, seq, t, st, flags=0, mode=F.MODE_ECO):
    st.mode = mode
    return F.make(t, box, 0, seq, st, flags)


def test_heartbeat_registers_box_and_dedupes(gw):
    fr = mk(1, 1, F.T_HEARTBEAT, status(danger=1, battery_pct=90))
    feed(gw, fr, T0)
    feed(gw, fr, T0 + 1)          # repeat of the same frame
    assert gw.stats["dup"] == 1 and gw.reg.get(1).frames == 1


def test_bad_frame_counted(gw):
    gw.handle(U.RxFrame(-90, 10, bytes(16)), T0)
    assert gw.stats["bad"] == 1


def test_box_fire_dispatches_everything_once(gw):
    gw.start_session(T0)
    feed(gw, mk(1, 1, F.T_ALERT, status(state=F.STATE_FIRE, reasons=F.R_GAS | F.R_FLAME, gas_class=1, flame=1), flags=F.F_ACK_REQ | F.F_PRIORITY), T0)
    sms = [m for m in gw.link.t.take_sent(U.SB_SEND_SMS)]
    assert len(sms) == 2                                          # one per number
    feed(gw, mk(1, 2, F.T_ALERT, status(state=F.STATE_FIRE, reasons=F.R_GAS | F.R_FLAME, gas_class=1, flame=1)), T0 + 10)
    assert gw.link.t.take_sent(U.SB_SEND_SMS) == []              # no second SMS in the same episode
    assert gw.alerts.last.top == 3
    kinds = [e["kind"] for e in gw.store.events()]
    assert "drone" in kinds and "alert" in kinds
    assert gw.link.t.take_sent(U.SB_DISPATCHED)
    gw.tick(T0 + 20)
    assert any(u.endswith("/api/alerts") for u, _ in gw.posts) and any(u.endswith("/api/email") for u, _ in gw.posts)
    assert list((gw.cfg.drone.missions_dir and __import__("pathlib").Path(gw.cfg.drone.missions_dir)).glob("mission_*.json"))


def test_bridge_emergency_suppresses_duplicate_sms(gw):
    gw.handle(U.Emergency(1, F.T_ALERT, 2), T0 - 5)
    feed(gw, mk(1, 1, F.T_ALERT, status(state=F.STATE_FIRE, reasons=F.R_GAS)), T0)
    assert gw.link.t.take_sent(U.SB_SEND_SMS) == []


def test_fire_latched_until_operator_ack_and_box_clear(gw):
    feed(gw, mk(1, 1, F.T_ALERT, status(state=F.STATE_FIRE, reasons=F.R_GAS)), T0)
    feed(gw, mk(1, 2, F.T_HEARTBEAT, status(state=F.STATE_NORMAL)), T0 + 600)
    assert gw.alerts.last.top == 3            # box recovered but nobody acknowledged
    gw.acknowledge(T0 + 700)
    assert gw.alerts.last.top != 3
    assert any(c[2] == F.C_RESET_FIRE for c in gw.down.sent)


def test_box_lost_and_neighbour_raised(gw):
    feed(gw, mk(1, 1, F.T_HEARTBEAT, status(danger=1)), T0)
    feed(gw, mk(2, 1, F.T_HEARTBEAT, status(danger=1)), T0)
    gw.tick(T0 + 2.5 * 600 + 60)
    levels = {(a.level, a.box) for a in gw.alerts.last.alerts}
    assert (4, 1) in levels and (4, 2) in levels


def test_last_gasp_is_l4_not_l3(gw):
    feed(gw, mk(1, 1, F.T_LAST_GASP, status(flags=F.SF_SUPPLY_FAULT)), T0)
    lv = {(a.level, a.box) for a in gw.alerts.last.alerts}
    assert (4, 1) in lv and (5, 1) in lv and gw.alerts.last.top == 4


def test_maintenance_flags(gw):
    feed(gw, mk(1, 1, F.T_HEARTBEAT, status(flags=F.SF_BATTERY_LOW | F.SF_HOUSING_HOT, battery_pct=9)), T0)
    a = [x for x in gw.alerts.last.alerts if x.level == 5][0]
    assert "battery" in a.reason and "housing" in a.reason


def test_threshold_policy_sent_once_per_class(gw):
    feed(gw, mk(1, 1, F.T_HEARTBEAT, status(danger=5)), T0)
    gw.tick(T0 + 1)
    gw.tick(T0 + 2)
    th = [c for c in gw.down.sent if c[2] == F.C_SET_THRESH]
    assert len(th) == 1 and th[0][3][0] == 35          # high-risk smoke_on 0.35


def test_vision_event_feeds_fusion(gw):
    feed(gw, mk(1, 1, F.T_STATE, status(state=F.STATE_SUSPICION, gas_class=1, reasons=F.R_GAS)), T0)
    before = gw.fusion_result.statistic
    gw.on_camera_event(1, "fire", 0.92, 80, T0 + 5)
    assert gw.fusion_result.statistic > before


def test_outbox_retries_when_dashboard_down(cfg):
    from ffn_gateway.app import Gateway
    calls = []

    def poster(url, body, tok=""):
        calls.append(url)
        if len(calls) <= 2:
            raise OSError("down")
    g = Gateway(cfg, None, poster=poster, load_models=False)
    g.disp.notify("X", 3, 1, "test", 36.8, 10.1, now=T0)
    assert g.disp.flush(T0) == 0 and g.store.outbox_pending()
    assert g.disp.flush(T0 + 6) >= 1 or g.disp.flush(T0 + 30) >= 1
    g.disp.flush(T0 + 400)
    assert not g.store.outbox_pending()


def test_status_view_serialisable(gw):
    feed(gw, mk(1, 1, F.T_HEARTBEAT, status(danger=2)), T0)
    json.dumps(gw.snapshot(T0 + 1))
