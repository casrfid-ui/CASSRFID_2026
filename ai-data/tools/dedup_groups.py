"""Near-duplicate grouping and leak-free split of a YOLO image set (D-Fire).

  python dedup_groups.py features DATA_DIR CACHE_DIR [--budget 150]   resumable, run until it prints "done"
  python dedup_groups.py cluster  DATA_DIR CACHE_DIR [--ham 4] [--color 12]
  python dedup_groups.py split    DATA_DIR CACHE_DIR OUT.csv [--seed 0]

Features per image: 64-bit difference hash (9x8 grayscale) + 4x4 RGB thumbnail (48 values).
Two images are near-duplicates when Hamming(dHash) <= ham AND mean |thumbnail difference| <= color
(the colour test removes matches between flat scenes such as sky or haze). Groups = connected components.
The split keeps every group in one split, stratified on the image-level class (background / fire / smoke / both).
Heuristic: frames of one video further apart than the thresholds are not linked; sites are unknown.
"""
import argparse, collections, json, os, random, sys, time
import numpy as np
from PIL import Image

SPLITS = ("train", "val", "test")
POP = np.array([bin(i).count("1") for i in range(256)], dtype=np.uint8)


def list_images(data):
    return [(s, f) for s in SPLITS for f in sorted(os.listdir(f"{data}/{s}/images"))]


def feat(path):
    im = Image.open(path); size = im.size
    im.draft("RGB", (320, 240))
    im = im.convert("RGB")
    g = np.asarray(im.convert("L").resize((9, 8), Image.BILINEAR), dtype=np.int16)
    bits = (g[:, 1:] > g[:, :-1]).ravel()
    h = np.packbits(bits)                                     # 8 bytes
    t = np.asarray(im.resize((4, 4), Image.BOX), dtype=np.uint8).ravel()
    return h, t, size


def cmd_features(a):
    items = list_images(a.data); n = len(items)
    os.makedirs(a.cache, exist_ok=True)
    p = f"{a.cache}/feat.npz"
    if os.path.exists(p):
        z = np.load(p); H, T, S, done = z["H"], z["T"], z["S"], int(z["done"])
    else:
        H = np.zeros((n, 8), np.uint8); T = np.zeros((n, 48), np.uint8); S = np.zeros((n, 2), np.int32); done = 0
    t0 = time.time()
    while done < n and time.time() - t0 < a.budget:
        s, f = items[done]
        try:
            H[done], T[done], S[done] = feat(f"{a.data}/{s}/images/{f}")
        except Exception as e:
            print("skip", s, f, type(e).__name__)
        done += 1
        if done % 500 == 0:
            np.savez(p, H=H, T=T, S=S, done=done)
    np.savez(p, H=H, T=T, S=S, done=done)
    print(f"{done}/{n}", "done" if done == n else "continue", flush=True)


def components(n, pairs):
    parent = list(range(n))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    for i, j in pairs:
        ri, rj = find(i), find(j)
        if ri != rj: parent[rj] = ri
    return np.array([find(i) for i in range(n)])


def cmd_cluster(a):
    z = np.load(f"{a.cache}/feat.npz"); H, T = z["H"], z["T"].astype(np.int16); n = len(H)
    assert int(z["done"]) == n, "features not finished"
    pairs = []; step = 400
    for i0 in range(0, n, step):
        x = H[i0:i0 + step, None, :] ^ H[None, :, :]
        d = POP[x].sum(2)
        ii, jj = np.nonzero(d <= a.ham)
        for i, j in zip(ii + i0, jj):
            if j > i and np.abs(T[i] - T[j]).mean() <= a.color: pairs.append((i, j))
    root = components(n, pairs)
    np.save(f"{a.cache}/group_{a.ham}_{a.color}.npy", root)
    sizes = collections.Counter(root.tolist())
    print(f"{n} images, {len(pairs)} linked pairs, {len(sizes)} groups, largest {max(sizes.values())}, singletons {sum(v == 1 for v in sizes.values())}")


def image_class(label_path):
    cl = set()
    for line in open(label_path):
        p = line.split()
        if len(p) >= 5: cl.add(int(p[0]))
    return {(): "background", (1,): "fire", (0,): "smoke", (0, 1): "both"}[tuple(sorted(cl))]


def cmd_split(a):
    items = list_images(a.data); n = len(items)
    root = np.load(f"{a.cache}/group_{a.ham}_{a.color}.npy")
    cache_cls = f"{a.cache}/classes.json"                    # label reading is slow on a network mount: cached
    if os.path.exists(cache_cls):
        cls = json.load(open(cache_cls))
    else:
        cls = [image_class(f"{a.data}/{s}/labels/{f.rsplit('.', 1)[0]}.txt") for s, f in items]
        json.dump(cls, open(cache_cls, "w"))
    assert len(cls) == n
    groups = collections.defaultdict(list)
    for i, r in enumerate(root): groups[int(r)].append(i)
    rng = random.Random(a.seed)
    order = sorted(groups.values(), key=lambda g: (-len(g), rng.random()))
    target = {"train": 0.70, "val": 0.15, "test": 0.15}
    tot = collections.Counter(cls)
    got = {s: collections.Counter() for s in SPLITS}; cnt = dict.fromkeys(SPLITS, 0)
    assign = {}
    for g in order:                                          # greedy: biggest groups first, to the split furthest below its target
        gc = collections.Counter(cls[i] for i in g)
        def deficit(s):
            return sum((target[s] * tot[c] - got[s][c]) / max(tot[c], 1) * v for c, v in gc.items())
        s = max(SPLITS, key=deficit)
        for i in g: assign[i] = s
        got[s].update(gc); cnt[s] += len(g)
    T = np.load(f"{a.cache}/feat.npz")["T"].astype(np.float64).reshape(n, 16, 3)
    lum = (T * [0.299, 0.587, 0.114]).sum(2).mean(1)         # mean luminance of the 4x4 thumbnail (0..255): day / night slices
    with open(a.out, "w") as f:
        f.write("orig_split,image,group,class,new_split,lum\n")
        for i, (s, name) in enumerate(items):
            f.write(f"{s},{name},{int(root[i])},{cls[i]},{assign[i]},{lum[i]:.1f}\n")
    print("new split sizes:", cnt)
    for s in SPLITS: print(s, dict(got[s]))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["features", "cluster", "split"])
    ap.add_argument("data"); ap.add_argument("cache"); ap.add_argument("out", nargs="?")
    ap.add_argument("--budget", type=float, default=150); ap.add_argument("--ham", type=int, default=4)
    ap.add_argument("--color", type=float, default=12); ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    {"features": cmd_features, "cluster": cmd_cluster, "split": cmd_split}[a.cmd](a)
