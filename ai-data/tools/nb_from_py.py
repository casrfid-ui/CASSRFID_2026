"""Builds a Jupyter notebook from a percent-format script and (optionally) executes it so the outputs are stored.

    python tools/nb_from_py.py notebooks/src/01_data.py notebooks/01_data.ipynb --run

Cells start with `# %%` (code) or `# %% [markdown]` (text; every following line is a comment `# ...`).
The .py is the source of truth: it diffs cleanly and runs as a script. The .ipynb is the readable artefact with stored outputs."""
import argparse
import pathlib
import re

import nbformat


def parse(text):
    cells, kind, buf = [], None, []

    def flush():
        if kind is None:
            return
        body = "\n".join(buf).strip("\n")
        if kind == "md":
            body = "\n".join(re.sub(r"^# ?", "", ln) for ln in body.splitlines())
            cells.append(nbformat.v4.new_markdown_cell(body))
        elif body.strip():
            cells.append(nbformat.v4.new_code_cell(body))

    for ln in text.splitlines():
        if ln.startswith("# %%"):
            flush()
            kind, buf = ("md" if "[markdown]" in ln else "code"), []
        else:
            buf.append(ln)
    flush()
    return cells


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--timeout", type=int, default=1800)
    a = ap.parse_args()
    nb = nbformat.v4.new_notebook(cells=parse(pathlib.Path(a.src).read_text(encoding="utf-8")))
    nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
    if a.run:
        from nbclient import NotebookClient
        NotebookClient(nb, timeout=a.timeout, kernel_name="python3",
                       resources={"metadata": {"path": str(pathlib.Path(a.dst).resolve().parent)}}).execute()
    nbformat.write(nb, a.dst)
    print("wrote", a.dst, len(nb.cells), "cells", "(executed)" if a.run else "")
