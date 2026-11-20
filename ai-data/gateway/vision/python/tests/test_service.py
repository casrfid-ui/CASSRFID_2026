"""Service tests. The model is the colour STUB: these tests prove plumbing and protocol, not detection quality."""
import io, json, subprocess, threading, urllib.request, urllib.error
from pathlib import Path
import numpy as np
import pytest
from PIL import Image
from gateway_vision import OnnxClassifier, preprocess, softmax
from gateway_vision.classifier import ImageError
from gateway_vision.server import make_server, MAX_BODY

ROOT = Path(__file__).resolve().parents[2]
STUB = ROOT / "models" / "plumbing_color_stub.onnx"
CAM_C = ROOT.parents[1] / "box" / "camera" / "c"


def jpeg(rgb, size=(160, 120)):
    b = io.BytesIO(); Image.new("RGB", size, rgb).save(b, "JPEG", quality=90); return b.getvalue()


@pytest.fixture(scope="module")
def srv(tmp_path_factory):
    store = tmp_path_factory.mktemp("recv")
    s = make_server(OnnxClassifier(STUB), "127.0.0.1", 0, store)
    t = threading.Thread(target=s.serve_forever, daemon=True); t.start()
    yield s, store
    s.shutdown()


def post(srv, body, headers=None, path="/v1/frame"):
    h = {"X-Box-Id": "3", "X-Req-Id": "7", "X-Time": "1700000000", "X-Reasons": "5", "Content-Type": "image/jpeg"}
    h.update(headers or {})
    h = {k: v for k, v in h.items() if v is not None}
    rq = urllib.request.Request(f"http://127.0.0.1:{srv[0].server_port}{path}", data=body, headers=h, method="POST")
    try:
        with urllib.request.urlopen(rq, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_preprocess_shape_and_range():
    x = preprocess(jpeg((10, 200, 30)))
    assert x.shape == (1, 3, 224, 224) and x.dtype == np.float32 and np.isfinite(x).all()
    with pytest.raises(ImageError): preprocess(b"not an image")
    with pytest.raises(ImageError): preprocess(b"")
    assert abs(softmax([1, 2, 3]).sum() - 1) < 1e-12


def test_stub_contract_and_distinct_outputs():
    c = OnnxClassifier(STUB)
    labels = {c.predict(jpeg(rgb)).label for rgb in [(255, 120, 30), (200, 200, 200), (60, 120, 60)]}
    assert labels == {"fire", "smoke", "background"}      # three colours, three classes: plumbing only
    p = c.predict(jpeg((255, 120, 30)))
    assert abs(sum(p.probs) - 1) < 1e-6 and 0 <= p.conf <= 1 and p.ms >= 0


def test_ok_answer_and_log(srv):
    code, d = post(srv, jpeg((255, 120, 30)))
    assert code == 200 and d["v"] == 1 and d["id"] == 7 and d["label"] == "fire" and 0 <= d["conf"] <= 1 and "ms" in d
    s, store = srv
    rec = [json.loads(l) for l in (store / "log.jsonl").read_text().splitlines()][-1]
    assert rec["box"] == 3 and rec["req"] == 7 and rec["label"] == "fire" and (store / rec["file"]).exists()


def test_error_paths_and_service_stays_up(srv):
    assert post(srv, b"garbage")[0] == 400
    assert post(srv, b"")[0] == 400
    assert post(srv, jpeg((1, 2, 3)), {"X-Req-Id": None})[0] == 400
    assert post(srv, jpeg((1, 2, 3)), {"X-Box-Id": "abc"})[0] == 400
    code, d = post(srv, jpeg((1, 2, 3)), path="/other"); assert code == 404 and d["id"] == 7
    code, d = post(srv, b"x" * (MAX_BODY + 10)); assert code == 413
    code, d = post(srv, jpeg((60, 120, 60))); assert code == 200 and d["label"] == "background"      # still alive
    with urllib.request.urlopen(f"http://127.0.0.1:{srv[0].server_port}/health") as r:
        assert json.loads(r.read())["ok"] is True


def test_concurrent_requests(srv):
    out = []
    def go(i): out.append(post(srv, jpeg((255, 120, 30)), {"X-Req-Id": str(100 + i)}))
    th = [threading.Thread(target=go, args=(i,)) for i in range(8)]
    [t.start() for t in th]; [t.join() for t in th]
    assert sorted(d["id"] for _, d in out) == list(range(100, 108)) and all(c == 200 for c, _ in out)


def test_answers_accepted_by_box_c_parser(srv):
    subprocess.run(["make", "-C", str(CAM_C), "cli"], check=True, capture_output=True)
    cli = CAM_C / "build" / "cam_cli"
    for rgb, want in [((255, 120, 30), 1), ((200, 200, 200), 2), ((60, 120, 60), 0)]:
        code, d = post(srv, jpeg(rgb), {"X-Req-Id": "42"})
        body = json.dumps(d, separators=(",", ":"))
        out = subprocess.run([str(cli)], input=f"P 42 {body}\n", capture_output=True, text=True).stdout.split()
        assert out[0] == "0" and int(out[1]) == want and abs(float(out[2]) - d["conf"]) < 1e-9
    # stale id and error body are refused by the box
    body = json.dumps(post(srv, jpeg((1, 2, 3)), {"X-Req-Id": "42"})[1])
    assert subprocess.run([str(cli)], input=f"P 43 {body}\n", capture_output=True, text=True).stdout.split()[0] == "-2"
    err = json.dumps(post(srv, b"garbage", {"X-Req-Id": "42"})[1])
    assert subprocess.run([str(cli)], input=f"P 42 {err}\n", capture_output=True, text=True).stdout.split()[0] == "-3"
