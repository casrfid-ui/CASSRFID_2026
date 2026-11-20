"""End to end, in process: the REAL gateway application fed with the scripted scenario frames drives the dashboard from
quiet to L3 fire; the operator acknowledgement on the dashboard reaches the gateway and the box recovers."""
from conftest import INGEST

from ffn_dashboard.demo import scenario as S
from ffn_gateway import uart_link as U
from ffn_gateway.app import Gateway
from ffn_gateway.config import load_config as gw_config

T0 = 1_793_800_000.0


class InProcessClient:
    def __init__(self, gw, clock):
        self.gw, self.clock = gw, clock

    def status(self):
        return self.gw.snapshot(self.clock())

    def timeline(self, limit=200):
        return self.gw.store.events(limit)

    def risk(self):
        return self.gw.slow.results

    def models(self):
        return self.gw.models.status

    def run(self, name, body):
        return self.gw.run_command(name, body, self.clock())


def run(tmp_path, make, push):
    now = [T0]
    clock = lambda: now[0]
    holder = {}
    poster = lambda url, body, token="": holder["c"].post(url.split("://", 1)[1].split("/", 1)[1].join(["/", ""]), json=body,
                                                         headers={"Authorization": "Bearer " + token}).raise_for_status()
    exchanger = lambda url, body, token="": holder["c"].post("/api/gateway/snapshot", json=body,
                                                             headers={"Authorization": "Bearer " + token}).json()
    gw = Gateway(gw_config(None, S.demo_gateway_config("http://dash.local", 0, str(tmp_path / "m"), push_s=0.0,
                                                       ingest_token="ingest-secret")),
                 U.Link(U.MemoryLink()), poster=poster, exchanger=exchanger)
    svc, c = make(client=None if push else InProcessClient(gw, clock))
    svc.clock = clock
    holder["c"] = c
    scen = S.Scenario(speed=1.0)

    def advance(seconds):
        for _ in range(int(seconds)):
            now[0] += 1
            for m in scen.step(now[0], gw):
                gw.handle(m, now[0])
            gw.tick(now[0])
            if push:
                gw.push_uplink(now[0])
            elif int(now[0]) % 2 == 0:
                svc.poll_once()
                svc._flush_commands()
    return gw, svc, c, advance


def check_story(gw, svc, c, advance):
    box = lambda ov, i: next(b for b in ov["boxes"] if b["id"] == i)
    advance(40)
    ov = c.get("/api/overview").json()
    assert ov["counts"]["boxes"] == 7 and ov["counts"]["online"] >= 6
    assert ov["level"]["top"] == 1 and box(ov, 2)["mode"] == "alert"
    assert box(ov, 1)["relayed"] is True and box(ov, 3)["relayed"] is False   # mesh relay flag
    advance(50)                                        # t = 90: smoke on box 6
    assert c.get("/api/overview").json()["level"]["top"] >= 2
    advance(30)                                        # t = 120: fire
    ov = c.get("/api/overview").json()
    assert ov["level"]["top"] == 3 and ov["fire_boxes"] == [6]
    assert box(ov, 6)["state"] == "fire" and set(box(ov, 6)["reasons"]) >= {"gas", "flame", "camera"}
    assert box(ov, 7)["state"] == "suspicion"
    alerts = c.get("/api/alerts").json()
    assert any(a["level"] == 3 for a in alerts)                          # pushed by the gateway dispatcher
    assert c.get("/api/missions").json()[0]["simulated"] is True          # drone mission
    assert c.get("/api/emails").json()[0]["status"] == "logged"           # email through the dashboard
    fire = c.get("/api/risk").json()["fire"]
    assert "isochrones" in fire and fire["source"]["n_boxes_detecting"] == 3 and not fire["source"]["used_as_ignition"]
    # operator acknowledges on the dashboard
    c.post("/api/ops/ack", json={})
    advance(40)
    ov = c.get("/api/overview").json()
    assert box(ov, 6)["state"] == "normal" and ov["level"]["top"] != 3
    assert ov["unacked_fire"] is None
    assert any(a["level"] == 5 and a["box"] == 4 for a in ov["alerts"])   # box 4 battery low
    assert any(a["level"] == 4 and a["box"] == 1 for a in ov["alerts"])   # box 1 silent since t = 40
    assert len(c.get("/api/boxes/6/series?hours=720").json()) >= 3


def test_end_to_end_pull_mode(tmp_path, make):
    check_story(*run(tmp_path, make, push=False))


def test_end_to_end_push_mode(tmp_path, make):
    check_story(*run(tmp_path, make, push=True))
