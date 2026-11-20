"""Writes the image lists and the Ultralytics data file for split_v2.

  python make_lists.py DATA_ROOT SPLIT_CSV OUT_DIR

DATA_ROOT is the folder that holds data/train|val|test/images and labels (the D-Fire folder).
Lists contain absolute paths (Ultralytics does not resolve relative ones from DATA_ROOT); the data file sets `path: DATA_ROOT`. Ultralytics finds a label by
replacing /images/ with /labels/ in the image path, so nothing is copied or moved.
Class ids follow the data: 0 = smoke, 1 = fire.
"""
import csv
import os
import sys


def main(root, split_csv, out):
    os.makedirs(out, exist_ok=True)
    lists = {"train": [], "val": [], "test": []}
    for r in csv.DictReader(open(split_csv)):
        p = os.path.join(os.path.abspath(root), "data", r["orig_split"], "images", r["image"])
        lists[r["new_split"]].append(p.replace(os.sep, "/"))
    for s, items in lists.items():
        with open(f"{out}/{s}.txt", "w") as f:
            f.write("\n".join(items) + "\n")
    yaml = (f"path: {os.path.abspath(root).replace(os.sep, '/')}\n"
            f"train: {os.path.abspath(out).replace(os.sep, '/')}/train.txt\n"
            f"val: {os.path.abspath(out).replace(os.sep, '/')}/val.txt\n"
            f"test: {os.path.abspath(out).replace(os.sep, '/')}/test.txt\n"
            "names:\n  0: smoke\n  1: fire\n")
    open(f"{out}/data_v2.yaml", "w").write(yaml)
    print({s: len(v) for s, v in lists.items()})


if __name__ == "__main__":
    main(*sys.argv[1:4])
