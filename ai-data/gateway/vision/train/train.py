"""Two-phase fine-tuning of a YOLO detector (smoke, fire) on split_v2, then ONNX export.

  python train.py --data lists/data_v2.yaml --extra-train deg/train_deg.txt --model yolov8n.pt --out runs
  python train.py ... --smoke          # 1 epoch on 1 % of the data: checks the whole chain before the real run

Phase 1: backbone frozen (freeze=10), higher learning rate: the head adapts to the two classes.
Phase 2: everything unfrozen from the phase-1 best weights, lower learning rate, cosine schedule.
Augmentation: Ultralytics online (mosaic, scale, flip, light HSV) + offline OV2640-like copies (build_degraded.py).
Hue is kept small on purpose: fire is orange, a large hue shift makes unrealistic training examples.
Requires: pip install ultralytics   (AGPL-3.0, see the fiche). Validation uses split_v2 `val`, never `test`.
"""
import argparse
import os
import shutil


def merged_list(data_yaml, extra, out_dir):
    """Training list = split_v2 train list + degraded copies. Returns a yaml path using it."""
    import yaml
    d = yaml.safe_load(open(data_yaml))
    if not extra:
        return data_yaml
    lines = []
    for p in [d["train"]] + extra:
        lines += [l for l in open(p).read().split("\n") if l.strip()]
    os.makedirs(out_dir, exist_ok=True)
    lst = os.path.join(out_dir, "train_mixed.txt")
    open(lst, "w").write("\n".join(lines) + "\n")
    d["train"] = os.path.abspath(lst).replace(os.sep, "/")
    out = os.path.join(out_dir, "data_mixed.yaml")
    yaml.safe_dump(d, open(out, "w"))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True); ap.add_argument("--extra-train", nargs="*", default=[])
    ap.add_argument("--model", default="yolov8n.pt"); ap.add_argument("--out", default="runs")
    ap.add_argument("--imgsz", type=int, default=640); ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--epochs1", type=int, default=10); ap.add_argument("--epochs2", type=int, default=60)
    ap.add_argument("--device", default=None); ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--seed", type=int, default=0); ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args()
    from ultralytics import YOLO

    data = merged_list(a.data, a.extra_train, os.path.join(a.out, "lists"))
    common = dict(data=data, imgsz=a.imgsz, batch=a.batch, device=a.device, workers=a.workers, seed=a.seed,
                  project=a.out, exist_ok=True, deterministic=True,
                  hsv_h=0.01, hsv_s=0.5, hsv_v=0.4, degrees=0.0, translate=0.1, scale=0.5, fliplr=0.5, flipud=0.0,
                  mosaic=1.0, mixup=0.1, close_mosaic=10)
    if a.smoke:
        common.update(fraction=0.01, workers=0)
        a.epochs1 = a.epochs2 = 1
    m = YOLO(a.model)
    m.train(name="phase1", epochs=a.epochs1, freeze=10, lr0=0.01, patience=0, **common)
    best1 = os.path.join(a.out, "phase1", "weights", "best.pt")
    m = YOLO(best1)
    m.train(name="phase2", epochs=a.epochs2, freeze=0, lr0=0.002, lrf=0.01, cos_lr=True, patience=15, **common)
    best = os.path.join(a.out, "phase2", "weights", "best.pt")
    onnx = YOLO(best).export(format="onnx", imgsz=a.imgsz, opset=13, simplify=True, dynamic=False)
    shutil.copyfile(onnx, os.path.join(a.out, "fire_smoke_yolo.onnx"))
    print("ONNX:", os.path.join(a.out, "fire_smoke_yolo.onnx"))


if __name__ == "__main__":
    main()
