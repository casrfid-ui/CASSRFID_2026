"""The five baselines the GRU has to beat. All see the same windows as the GRU."""
import numpy as np


class Baselines:
    """fit(Xtr, Ytr, meta_tr) then scores(Xte, meta_te) -> {name: (N, 3) scores}. Hyper-parameters are fixed in advance."""

    def __init__(self, seed=0):
        self.seed = seed
        self.models = {}

    @staticmethod
    def _cur(X):
        return X[:, -1, :]

    @staticmethod
    def _flat(X):
        return X.reshape(len(X), -1)

    def fit(self, X, Y, meta=None):
        from sklearn.ensemble import HistGradientBoostingClassifier
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
        for h in range(Y.shape[1]):
            y = Y[:, h]
            if y.sum() == 0 or y.sum() == len(y):
                self.models[("const", h)] = float(y.mean()); continue
            self.models[("lr_cur", h)] = make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=500)).fit(self._cur(X), y)
            self.models[("lr_win", h)] = make_pipeline(StandardScaler(), LogisticRegression(C=0.05, max_iter=500)).fit(self._flat(X), y)
            self.models[("gbm", h)] = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.08, max_iter=120, random_state=self.seed).fit(self._flat(X), y)
        return self

    def scores(self, X, meta):
        H = len(self.models) and max(h for _, h in self.models) + 1
        out = {"persistence": np.repeat(meta["fire_today"][:, None], H, 1).astype(float),
               "fwi_threshold": np.repeat(meta["fwi"][:, None], H, 1).astype(float)}
        for name, feats in (("lr_cur", self._cur), ("lr_win", self._flat), ("gbm", self._flat)):
            s = np.zeros((len(X), H))
            for h in range(H):
                m = self.models.get((name, h))
                s[:, h] = m.predict_proba(feats(X))[:, 1] if m is not None else self.models.get(("const", h), 0.0)
            out[name] = s
        return out
