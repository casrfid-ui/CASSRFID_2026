from state_machine import (FIRE, NORMAL, SUSPICION, R_CAMERA, R_FLAME, R_FWI, R_GAS, Config, Inputs, StateMachine)


def step(sm, **kw):
    return sm.step(Inputs(**kw))


def into_suspicion(sm):
    out = step(sm, gas_smoke=True)
    assert out.state == SUSPICION
    return out


def test_starts_normal_camera_and_gps_off():
    out = step(StateMachine())
    assert (out.state, out.camera_on, out.gps_on, out.actuator) == (NORMAL, False, False, False)


def test_scan_interval_by_mode():
    sm = StateMachine()
    assert step(sm, fwi_mode="eco").interval_s == 300
    assert step(sm, fwi_mode="alert").interval_s == 30
    assert step(sm, battery_low=True).interval_s == 3600


def test_gas_smoke_starts_suspicion_with_camera_and_gps():
    out = into_suspicion(StateMachine())
    assert out.camera_on and out.gps_on and out.interval_s == 30
    assert out.reasons & R_GAS


def test_single_flame_read_is_ignored_two_are_not():
    sm = StateMachine()
    assert step(sm, flame=True).state == NORMAL
    assert step(sm, flame=False).state == NORMAL
    assert step(sm, flame=True).state == NORMAL
    out = step(sm, flame=True)
    assert out.state == SUSPICION and out.reasons & R_FLAME


def test_camera_confirmation_gives_fire_and_three_alert_frames():
    sm = StateMachine()
    into_suspicion(sm)
    out = step(sm, gas_smoke=True, camera=("smoke", 0.9))
    assert out.state == FIRE
    assert ("alert", 3) in out.frames and out.actuator
    assert out.reasons & R_CAMERA


def test_weak_or_background_camera_does_not_confirm():
    sm = StateMachine()
    into_suspicion(sm)
    assert step(sm, gas_smoke=True, camera=("fire", 0.4)).state == SUSPICION
    assert step(sm, gas_smoke=True, camera=("background", 0.99)).state == SUSPICION


def test_gas_and_flame_agree_gives_fire_without_camera():
    sm = StateMachine()
    step(sm, gas_smoke=True)
    step(sm, gas_smoke=True, flame=True)
    out = step(sm, gas_smoke=True, flame=True)
    assert out.state == FIRE


def test_fire_needs_a_second_witness():
    """Gas alone, or flame alone, for a long time never reaches Fire."""
    for kw in ({"gas_smoke": True}, {"flame": True}):
        sm = StateMachine()
        states = {step(sm, **kw).state for _ in range(200)}
        assert FIRE not in states


def test_suspicion_clears_after_quiet_scans():
    sm = StateMachine()
    into_suspicion(sm)
    states = [step(sm).state for _ in range(Config().clear_scans)]
    assert states[-1] == NORMAL and SUSPICION in states[:-1]


def test_trigger_resets_the_clear_counter():
    sm = StateMachine()
    into_suspicion(sm)
    for _ in range(Config().clear_scans - 1):
        step(sm)
    step(sm, gas_smoke=True)
    assert step(sm).state == SUSPICION


def test_fire_is_latched_until_reset_or_long_all_clear():
    sm = StateMachine()
    into_suspicion(sm)
    step(sm, gas_smoke=True, camera=("fire", 0.95))
    assert step(sm, dt_s=600).state == FIRE
    assert step(sm, dt_s=600).state == FIRE
    assert step(sm, dt_s=600).state == NORMAL        # 1800 s all clear
    sm2 = StateMachine()
    into_suspicion(sm2)
    step(sm2, gas_smoke=True, camera=("fire", 0.95))
    sm2.reset()
    assert step(sm2).state == NORMAL


def test_trigger_inside_fire_restarts_the_hold():
    sm = StateMachine()
    into_suspicion(sm)
    step(sm, gas_smoke=True, camera=("fire", 0.95))
    step(sm, dt_s=1500)
    step(sm, gas_smoke=True, dt_s=30)
    assert step(sm, dt_s=1500).state == FIRE


def test_camera_is_woken_at_most_every_30_seconds():
    sm = StateMachine()
    woke = [step(sm, gas_smoke=True, dt_s=10).camera_on for _ in range(9)]
    assert sum(woke) == 3


def test_pump_prewets_only_on_high_fwi_and_suspicion():
    sm = StateMachine()
    assert step(sm, fwi_danger=4).actuator is False
    out = step(sm, gas_smoke=True, fwi_danger=4)
    assert out.actuator and out.reasons & R_FWI
    sm2 = StateMachine()
    assert step(sm2, gas_smoke=True, fwi_danger=1).actuator is False


def test_last_gasp_is_sent_once():
    sm = StateMachine()
    first = step(sm, housing_hot=True)
    second = step(sm, housing_hot=True)
    assert first.last_gasp and ("last_gasp", 3) in first.frames
    assert not second.last_gasp


def test_survival_ignores_gas_but_flame_still_wakes():
    sm = StateMachine()
    assert step(sm, battery_low=True, gas_smoke=True).state == NORMAL
    step(sm, battery_low=True, flame=True)
    out = step(sm, battery_low=True, flame=True)
    assert out.state == SUSPICION and not out.camera_on


def test_frames_only_on_change_or_heartbeat():
    sm = StateMachine()
    quiet = [step(sm, dt_s=30).frames for _ in range(19)]
    assert all(f == [] for f in quiet)
    assert step(sm, dt_s=30).frames == [("heartbeat", 1)]
    assert step(sm, gas_smoke=True).frames == [("state_change", 1)]


def test_reasons_clear_back_in_normal():
    sm = StateMachine()
    into_suspicion(sm)
    for _ in range(Config().clear_scans):
        out = step(sm)
    assert out.state == NORMAL and out.reasons == 0


def test_first_flame_read_shortens_the_next_sleep():
    sm = StateMachine()
    assert step(sm, fwi_mode="eco").interval_s == 300
    out = step(sm, flame=True)                         # one read: still Normal, but look again soon
    assert out.state == NORMAL and out.interval_s == 30
    assert step(sm, flame=False).interval_s == 300     # the read was not confirmed: back to the Eco pace
    out = step(sm, flame=True)
    assert out.interval_s == 30
    assert step(sm, flame=True).state == SUSPICION     # confirmed at the second read, 30 s later


def test_recheck_never_lengthens_and_can_be_switched_off():
    sm = StateMachine()
    assert step(sm, flame=True, fwi_mode="alert").interval_s == 30
    sm = StateMachine(Config(flame_recheck_s=0))
    assert step(sm, flame=True).interval_s == 300
    sm = StateMachine(Config(flame_recheck_s=10))
    assert step(sm, flame=True, fwi_mode="alert").interval_s == 10
    sm = StateMachine()
    assert step(sm, flame=True, battery_low=True).interval_s == 30   # Survival: one short extra wake to confirm
