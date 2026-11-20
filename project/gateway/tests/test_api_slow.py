import json
import urllib.request

from ffn_gateway.api import serve
from ffn_gateway.ffp import frame as F
from ffn_gateway import uart_link as U

T0 = 1_793_800_000.0


def test_models_status_and_placeholders(gw):
    st = gw.models.status
    assert st["autoencoder"]["state"] == "placeholder" and st["gas_classifier"]["state"] == "placeholder"
    assert st["risk_gru"]["state"] == "ok" and st["fwi_forecast"]["state"] == "ok"


def test_slow_path_runs_on_box_data(gw):
    t = F.Telem(temp_c100=3100, rh_x2=60, wind_kmh=15, rain_x10=0, ffmc_x2_5=int(88 * 2.5), dmc=60, dc=300, isi_x5=30, bui=80)
    gw.handle(U.RxFrame(-90, 40, F.make(F.T_TELEM, 1, 0, 1, t).encode()), T0)
    gw.handle(U.RxFrame(-90, 40, F.make(F.T_HEARTBEAT, 1, 0, 2, F.Status(danger=4, fwi_x2=40)).encode()), T0)
    r = gw.slow.run_once(T0)
    assert "errors" not in r, r.get("errors")
    assert 1 in r["risk"] and r["risk"][1]["level"] in ("low", "moderate", "high")
    assert len(r["fwi_forecast"][1]) == 3


def test_fire_geometry_marks_wind_direction_simulated(gw):
    t = F.Telem(temp_c100=3500, rh_x2=40, wind_kmh=20, ffmc_x2_5=225, dmc=80, dc=400, isi_x5=60, bui=100)
    gw.handle(U.RxFrame(-90, 40, F.make(F.T_TELEM, 1, 0, 1, t).encode()), T0)
    gw.handle(U.RxFrame(-90, 40, F.make(F.T_ALERT, 1, 0, 2, F.Status(state=F.STATE_FIRE, reasons=1, gas_class=1, gas_score=250, band=(100, 90, 80))).encode()), T0 + 1)
    fire = gw.slow.results["fire"]
    assert fire["wind_direction_simulated"] is True
    assert set(fire["isochrones"]) == {"15", "30", "60"}
    assert fire["isochrones"]["60"]["area_m2"] > fire["isochrones"]["15"]["area_m2"]


def test_api(gw):
    gw.cfg.api_port = 0
    gw.cfg.api_token = "tok"
    srv = serve(gw)
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def call(path, body=None, tok="tok"):
        req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(), method="GET" if body is None else "POST")
        if tok:
            req.add_header("Authorization", "Bearer " + tok)
        try:
            with urllib.request.urlopen(req, timeout=3) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())
    try:
        assert call("/health", tok="")[0] == 200
        assert call("/v1/status", tok="")[0] == 401
        assert call("/v1/status")[0] == 200
        assert call("/v1/models")[1]["autoencoder"]["state"] == "placeholder"
        assert call("/v1/camera-event", {"box": 1, "label": "fire", "conf": 0.9})[0] == 200
        assert call("/v1/camera-event", {"box": 1})[0] == 400
        assert call("/v1/cmd", {"box": 1, "cmd": "ping"})[0] == 200
        assert call("/v1/sim/weather", {"box": 1, "wind_kmh": 20, "rain_mm": 1.5})[0] == 200
        assert call("/v1/test/sms", {})[0] == 200
        assert call("/v1/nope")[0] == 404
        assert len(call("/v1/timeline")[1]) >= 1
    finally:
        srv.shutdown()
