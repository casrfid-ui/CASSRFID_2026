"""Sends photos to the gateway service exactly like a box does (protocol v1) and prints the verdicts.

  python -m gateway_vision.client http://127.0.0.1:8080 photo1.jpg photo2.jpg [--folder DIR] [--box-id 1] [--debug]
                                   [--annotate OUT_DIR] [--csv results.csv]

--debug asks for the detected boxes (POST /v1/frame?debug=1); --annotate writes copies with the boxes drawn.
A box never uses --debug: its answer must stay within the 256-byte buffer of the firmware.
"""
import argparse
import csv
import json
import os
import time
import urllib.error
import urllib.request

IMAGES = (".jpg", ".jpeg", ".png", ".bmp")


def send_photo(url, jpeg, box_id=1, req_id=1, reasons=0, unix_s=None, debug=False, timeout=10.0):
    """POST one image. Returns dict(status, answer, round_trip_ms); answer is the parsed JSON body (or None)."""
    rq = urllib.request.Request(
        url.rstrip("/") + "/v1/frame" + ("?debug=1" if debug else ""), data=jpeg, method="POST",
        headers={"X-Box-Id": str(box_id), "X-Req-Id": str(req_id), "X-Time": str(int(unix_s if unix_s is not None else time.time())),
                 "X-Reasons": str(reasons), "Content-Type": "image/jpeg"})
    t = time.perf_counter()
    try:
        with urllib.request.urlopen(rq, timeout=timeout) as r:
            status, body = r.status, r.read()
    except urllib.error.HTTPError as e:
        status, body = e.code, e.read()
    except Exception as e:
        return {"status": 0, "answer": {"error": f"{type(e).__name__}: {e}"}, "round_trip_ms": round((time.perf_counter() - t) * 1000)}
    try:
        ans = json.loads(body)
    except Exception:
        ans = None
    return {"status": status, "answer": ans, "round_trip_ms": round((time.perf_counter() - t) * 1000)}


def draw_boxes(path_or_bytes, boxes, out_path, label=None):
    """Writes a copy of the image with the boxes [class, score, x1, y1, x2, y2] drawn (fire red, smoke grey)."""
    import io
    from PIL import Image, ImageDraw
    src = io.BytesIO(path_or_bytes) if isinstance(path_or_bytes, (bytes, bytearray)) else path_or_bytes
    im = Image.open(src).convert("RGB")
    d = ImageDraw.Draw(im)
    w = max(2, im.size[0] // 300)
    for c, s, x1, y1, x2, y2 in boxes:
        col = (230, 40, 20) if c == "fire" else (150, 150, 160)
        d.rectangle([x1, y1, x2, y2], outline=col, width=w)
        d.text((x1 + 3, max(0, y1 - 12)), f"{c} {s:.2f}", fill=col)
    if label:
        d.text((8, 8), label, fill=(255, 255, 0))
    im.save(out_path, quality=92, **({"format": "JPEG"} if hasattr(out_path, "write") else {}))


def list_images(paths, folder=None):
    out = list(paths)
    if folder:
        out += sorted(os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(IMAGES))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("url"); ap.add_argument("images", nargs="*"); ap.add_argument("--folder")
    ap.add_argument("--box-id", type=int, default=1); ap.add_argument("--reasons", type=int, default=0)
    ap.add_argument("--debug", action="store_true"); ap.add_argument("--annotate"); ap.add_argument("--csv")
    a = ap.parse_args(argv)
    files = list_images(a.images, a.folder)
    if not files:
        ap.error("no image given")
    if a.annotate:
        os.makedirs(a.annotate, exist_ok=True)
    rows = []
    print(f"{'image':36s} {'status':>6s} {'label':>10s} {'conf':>6s} {'model ms':>9s} {'round trip ms':>14s}")
    for i, f in enumerate(files, 1):
        jpeg = open(f, "rb").read()
        r = send_photo(a.url, jpeg, a.box_id, i, a.reasons, debug=a.debug or bool(a.annotate))
        ans = r["answer"] or {}
        row = {"image": os.path.basename(f), "status": r["status"], "label": ans.get("label", ""), "conf": ans.get("conf", ""),
               "model_ms": ans.get("ms", ""), "round_trip_ms": r["round_trip_ms"], "error": ans.get("error", "")}
        rows.append(row)
        print(f"{row['image'][:36]:36s} {row['status']:6d} {row['label'] or row['error'][:10]:>10s} {row['conf']!s:>6s} "
              f"{row['model_ms']!s:>9s} {row['round_trip_ms']:>14d}")
        if a.annotate and ans.get("boxes") is not None:
            draw_boxes(f, ans["boxes"], os.path.join(a.annotate, os.path.basename(f)), f"{row['label']} {row['conf']}")
    if a.csv:
        with open(a.csv, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    return rows


if __name__ == "__main__":
    main()
