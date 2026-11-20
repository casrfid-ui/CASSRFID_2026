from conftest import INGEST, FakeClient

ALERT = {"alert_id": "F1793800000", "level": 3, "level_name": "L3 fire", "box": 1, "reason": "box FIRE (gas+flame)",
         "lat": 36.78, "lon": 8.69, "text": "FIRE ALERT box 1", "t": 1793800000.0}


def test_ingest_requires_the_gateway_token(make):
    _, c = make()
    assert c.post("/api/alerts", json=ALERT).status_code == 401
    assert c.post("/api/alerts", json=ALERT, headers={"Authorization": "Bearer wrong"}).status_code == 401
    r = c.post("/api/alerts", json=ALERT, headers=INGEST)
    assert r.status_code == 200 and r.json()["level"] == 3 and r.json()["acked"] is False


def test_alert_is_listed_and_unacked_fire_shown_in_overview(make):
    _, c = make()
    c.post("/api/alerts", json=ALERT, headers=INGEST)
    assert c.get("/api/alerts").json()[0]["alert_id"] == "F1793800000"
    assert c.get("/api/overview").json()["unacked_fire"]["box"] == 1


def test_bad_payload_rejected(make):
    _, c = make()
    assert c.post("/api/alerts", json={"level": 9}, headers=INGEST).status_code == 422


def test_mission_and_email_ingest(make):
    svc, c = make()
    m = {"id": "F1", "simulated": True, "target": {"lat": 36.78, "lon": 8.69}, "base": {"lat": 36.79, "lon": 8.70},
         "items": [{"seq": 0, "command": 22, "name": "TAKEOFF"}]}
    assert c.post("/api/missions", json=m, headers=INGEST).status_code == 200
    assert c.get("/api/missions").json()[0]["id"] == "F1"
    e = c.post("/api/email", json={"to": "ops@example.org", "subject": "FIRE", "body": "x", "alert_id": "F1"}, headers=INGEST).json()
    assert e["status"] == "logged"                     # no SMTP configured
    assert c.get("/api/emails").json()[0]["recipient"] == "ops@example.org"


def test_pull_mode_poll_stores_snapshot_events_and_samples(make):
    fc = FakeClient()
    fc.state["boxes"] = [{"id": 1, "name": "A", "lat": 36.7, "lon": 8.6, "age_s": 3, "rssi": -96, "snr": 7, "frames": 4, "lost": False,
                          "status": {"state": 1, "mode": 1, "reasons": 1, "gas_score": 0.4, "gas_class": 1, "flame": 0, "cam_label": 0,
                                     "cam_valid": 1, "cam_conf": 0.1, "fwi": 41.0, "danger": 4, "battery_pct": 80, "flags": 0, "bands": [0.2, 0.1, 0.0]}}]
    svc, c = make(client=fc)
    assert svc.poll_once()
    ov = c.get("/api/overview").json()
    b = ov["boxes"][0]
    assert b["state"] == "suspicion" and b["reasons"] == ["gas"] and b["fwi"]["danger_name"] == "very high"
    assert ov["link"]["online"] is True
    assert c.get("/api/timeline").json()[0]["text"] == "suspicion"
    assert len(c.get("/api/boxes/1/series").json()) == 1


def test_gateway_down_is_visible(make):
    fc = FakeClient()
    svc, c = make(client=fc)
    svc.poll_once()
    fc.fail = True
    assert not svc.poll_once()
    link = c.get("/api/overview").json()["link"]
    assert link["online"] is False and "down" in link["error"]


def test_operator_ack_goes_to_gateway_in_pull_mode(make):
    fc = FakeClient()
    svc, c = make(client=fc)
    c.post("/api/alerts", json=ALERT, headers=INGEST)
    r = c.post("/api/ops/ack", json={}).json()
    assert r["status"] == "done" and fc.calls[0][0] == "ack"
    assert c.get("/api/alerts").json()[0]["acked"] is True


def test_commands_queue_when_gateway_unreachable_then_flush(make):
    fc = FakeClient()
    svc, c = make(client=fc)
    fc.fail = True
    assert c.post("/api/ops/command", json={"cmd": "ping", "box": 2}).json()["status"] == "queued"
    fc.fail = False
    svc._flush_commands()
    assert fc.calls == [("ping", {"box": 2})]


def test_push_mode_returns_queued_commands_once(make):
    svc, c = make()                      # no gateway_url: push mode
    c.post("/api/ops/command", json={"cmd": "reset_fire", "box": 1})
    snap = {"status": {"t": 5.0, "assessment": {"top": 0, "alerts": []}, "boxes": []}, "timeline": []}
    r = c.post("/api/gateway/snapshot", json=snap, headers=INGEST).json()
    assert r["commands"][0]["name"] == "reset_fire"
    assert c.post("/api/gateway/snapshot", json=snap, headers=INGEST).json()["commands"] == []
    assert c.get("/api/overview").json()["link"]["mode"] == "push"


def test_threshold_command_validation(make):
    _, c = make(client=FakeClient())
    assert c.post("/api/ops/command", json={"cmd": "thresholds", "box": 1, "smoke_on": 0.2, "smoke_off": 0.4, "camera": 0.6}).status_code == 400
    assert c.post("/api/ops/command", json={"cmd": "explode", "box": 1}).status_code == 400
    assert c.post("/api/ops/command", json={"cmd": "thresholds", "box": 1, "smoke_on": 0.4, "smoke_off": 0.2, "camera": 0.6}).status_code == 200


def test_operator_token_enforced_when_set(make):
    _, c = make(operator_token="op")
    assert c.post("/api/ops/ack", json={}).status_code == 401
    assert c.post("/api/ops/ack", json={}, headers={"Authorization": "Bearer op"}).status_code == 200
    assert c.get("/api/config").json()["operator_token_required"] is True
