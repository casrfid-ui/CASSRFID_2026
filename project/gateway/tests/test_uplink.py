"""Dashboard uplink: the gateway pushes its snapshot and runs the operator commands the dashboard answers with."""
from ffn_gateway import uart_link as U
from ffn_gateway.app import Gateway
from ffn_gateway.ffp import frame as F

T0 = 1_793_800_000.0


def make(cfg, answers):
    sent = []

    def exchanger(url, body, token=""):
        sent.append((url, body))
        return answers.pop(0) if answers else {"commands": []}

    g = Gateway(cfg, U.Link(U.MemoryLink()), poster=lambda *a, **k: None, exchanger=exchanger)
    return g, sent


def test_push_sends_snapshot_and_new_events_only(cfg):
    g, sent = make(cfg, [])
    st = F.Status(state=F.STATE_FIRE, reasons=F.R_GAS | F.R_FLAME, danger=3)
    g.handle(U.RxFrame(-90, 40, F.make(F.T_ALERT, 1, 0, 1, st, 0).encode()), T0)
    g.push_uplink(T0 + 1)
    url, body = sent[0]
    assert url.endswith("/api/gateway/snapshot")
    assert body["status"]["assessment"]["top"] == 3 and body["timeline"]
    g.push_uplink(T0 + 2)
    assert sent[1][1]["timeline"] == []          # nothing new since the last push


def test_commands_from_dashboard_are_executed(cfg):
    g, sent = make(cfg, [{"commands": [{"id": 1, "name": "ping", "body": {"box": 2}},
                                       {"id": 2, "name": "nonsense", "body": {}}]}])
    g.push_uplink(T0)
    assert g.uplink["commands"] == 1
    texts = [e["text"] for e in g.store.events(50)]
    assert any("dashboard command ping" in t for t in texts)
    assert any("refused" in t for t in texts)


def test_push_failure_is_counted_not_raised(cfg):
    def boom(url, body, token=""):
        raise OSError("no route")
    g = Gateway(cfg, U.Link(U.MemoryLink()), poster=lambda *a, **k: None, exchanger=boom)
    assert g.push_uplink(T0) is None and g.uplink["fail"] == 1
