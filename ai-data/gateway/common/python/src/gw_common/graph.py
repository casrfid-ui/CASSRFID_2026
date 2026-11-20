"""Numpy message passing for the mesh model (inference). Training uses the same equations in torch.

A graph is given by edge lists `src -> dst` (every link appears in both directions) and edge features `e` (E, F).
Layer:  gate_ij = sigmoid(w_g . e_ij + b_g)
        m_i     = sum_j gate_ij * h_j / (sum_j gate_ij + eps)        (weighted mean of the neighbours)
        h_i'    = relu(W_self h_i + W_nb m_i + b)
Nodes without neighbours get m_i = 0 (so the layer reduces to a dense layer on the node itself)."""
import numpy as np

EPS = 1e-6


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def aggregate(h, src, dst, e, w_g, b_g):
    n = h.shape[0]
    if len(src) == 0:
        return np.zeros_like(h)
    gate = _sigmoid(e @ w_g + b_g)                      # (E,)
    num = np.zeros_like(h)
    np.add.at(num, dst, gate[:, None] * h[src])
    den = np.zeros(n)
    np.add.at(den, dst, gate)
    return num / (den[:, None] + EPS)


def layer(h, src, dst, e, p):
    m = aggregate(h, src, dst, e, p["w_g"], p["b_g"])
    return np.maximum(h @ p["w_self"].T + m @ p["w_nb"].T + p["b"], 0.0)


def forward(x, src, dst, e, params):
    """params: {'layers': [dict,...], 'head_w': (1,H), 'head_b': (1,)}. Returns logits (N,)."""
    h = np.asarray(x, np.float64)
    for p in params["layers"]:
        h = layer(h, src, dst, e, p)
    return (h @ params["head_w"].T + params["head_b"])[:, 0]
