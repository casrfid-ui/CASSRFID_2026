"""Run a notebook and store its outputs (text, values, figures) in the file.

  python tools/run_notebook.py notebooks/vision/01_dataset_and_labels.ipynb [more.ipynb ...]

Same job as `jupyter nbconvert --execute --inplace`, for machines where Jupyter is not installed.
Cells run in order in one namespace, from the notebook's own folder. Printed text goes to a stream
output, the value of a last expression to a result, every figure shown with plt.show() to an image.
The first error stops the run and is stored in the cell. Notebooks keep their outputs in Git: they are
the readable record of what the code did."""
import ast
import base64
import contextlib
import io
import json
import os
import sys
import time
import traceback

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def run(path):
    nb = json.load(open(path))
    os.chdir(os.path.dirname(os.path.abspath(path)))
    g = {"__name__": "__main__"}
    figs = []

    def show(*a, **k):
        for n in plt.get_fignums():
            buf = io.BytesIO()
            plt.figure(n).savefig(buf, format="png", dpi=100, bbox_inches="tight")
            figs.append(base64.b64encode(buf.getvalue()).decode())
        plt.close("all")

    plt.show = show
    count, t0, ok = 0, time.time(), True
    for i, c in enumerate(nb["cells"]):
        if c["cell_type"] != "code":
            continue
        if not ok:
            c["outputs"], c["execution_count"] = [], None
            continue
        count += 1
        src = "".join(c["source"])
        out, buf, figs[:] = [], io.StringIO(), []
        value = None
        try:
            tree = ast.parse(src)
            last = tree.body.pop() if tree.body and isinstance(tree.body[-1], ast.Expr) else None
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                exec(compile(tree, f"cell{i}", "exec"), g)
                if last is not None:
                    value = eval(compile(ast.Expression(last.value), f"cell{i}", "eval"), g)
        except Exception:
            ok = False
            err = traceback.format_exc().splitlines()
            out.append({"output_type": "error", "ename": "Error", "evalue": err[-1], "traceback": err})
            print(f"FAILED cell {i}: {err[-1]}")
        text = buf.getvalue()
        if text:
            out.insert(0, {"output_type": "stream", "name": "stdout", "text": text.splitlines(True)})
        for f in figs:
            out.append({"output_type": "display_data", "metadata": {}, "data": {"image/png": f, "text/plain": ["<Figure>"]}})
        if value is not None:
            out.append({"output_type": "execute_result", "execution_count": count, "metadata": {}, "data": {"text/plain": repr(value).splitlines(True)}})
        c["outputs"], c["execution_count"] = out, count
    json.dump(nb, open(path, "w"), indent=1)
    print(f"{os.path.basename(path)}: {'OK' if ok else 'FAILED'} ({count} code cells, {time.time() - t0:.0f} s)")
    return ok


if __name__ == "__main__":
    sys.exit(0 if all([run(p) for p in sys.argv[1:]]) else 1)
