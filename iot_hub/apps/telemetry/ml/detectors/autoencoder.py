"""Детектор аномалий на автоэнкодере (PyTorch).

Учит нормальную ДИНАМИКУ на каузальных окнах сырых значений. Аномалия score =
ошибка реконструкции окна: участок, не вписывающийся в выученную форму (в т.ч.
залипание — обрыв динамики в плоский хвост), реконструируется плохо → высокий
score. Это берёт stuck, который z-score и Isolation Forest структурно не ловят.

Обучение unsupervised на всех окнах ряда (метки не используются — честно по
сравнению с z-score/IF; метки только в evaluation). Порог по умолчанию —
перцентиль ошибки реконструкции на train, а не по меткам.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..base import AnomalyDetector, DetectionResult
from ..dataset import TimeSeries
from ..torch_utils import (
    set_torch_determinism, make_causal_windows, global_standardize, MLPAutoencoder,
)


@dataclass
class AutoencoderDetector(AnomalyDetector):
    """threshold=None → калибровка порога по перцентилю ошибки на train."""
    window: int = 72
    threshold: float | None = None
    latent_dim: int = 8
    epochs: int = 150
    lr: float = 1e-3
    batch_size: int = 256
    threshold_percentile: float = 98.0
    random_state: int = 42
    name: str = "autoencoder"
    _model: object = field(default=None, init=False, repr=False)
    _stats: tuple = field(default=None, init=False, repr=False)
    _threshold: float | None = field(default=None, init=False, repr=False)

    def _windows(self, series: TimeSeries):
        return make_causal_windows(np.asarray(series.values, float), self.window)

    def fit(self, series: TimeSeries) -> "AutoencoderDetector":
        import torch

        set_torch_determinism(self.random_state)
        W, warmup = self._windows(series)
        Wn, self._stats = global_standardize(W[~warmup])
        X = torch.from_numpy(Wn)

        self._model = MLPAutoencoder(self.window, self.latent_dim)
        opt = torch.optim.Adam(self._model.parameters(), lr=self.lr)
        loss_fn = torch.nn.MSELoss()
        self._model.train()
        for _ in range(self.epochs):
            opt.zero_grad()
            loss = loss_fn(self._model(X), X)
            loss.backward()
            opt.step()

        train_err = self._reconstruction_error(Wn)
        self._threshold = (
            self.threshold if self.threshold is not None
            else float(np.percentile(train_err, self.threshold_percentile))
        )
        return self

    def _reconstruction_error(self, Wn: np.ndarray) -> np.ndarray:
        import torch

        self._model.eval()
        with torch.no_grad():
            X = torch.from_numpy(Wn.astype(np.float32))
            recon = self._model(X).numpy()
        return ((Wn - recon) ** 2).mean(axis=1)

    def score(self, series: TimeSeries) -> np.ndarray:
        if self._model is None:
            self.fit(series)
        W, warmup = self._windows(series)
        Wn, _ = global_standardize(W, stats=self._stats)
        scores = np.zeros(len(series), dtype=float)
        scores[~warmup] = self._reconstruction_error(Wn[~warmup])
        return scores

    def predict(self, series: TimeSeries) -> DetectionResult:
        if self._model is None:
            self.fit(series)
        scores = self.score(series)
        _, warmup = self._windows(series)
        predictions = (scores >= self._threshold) & ~warmup
        return DetectionResult(
            scores=scores,
            predictions=predictions,
            warmup_mask=warmup,
            threshold=self._threshold,
            meta={
                "method": self.name,
                "window": self.window,
                "params": {
                    "threshold": self._threshold,
                    "latent_dim": self.latent_dim,
                    "epochs": self.epochs,
                    "lr": self.lr,
                    "threshold_percentile": self.threshold_percentile,
                    "random_state": self.random_state,
                    "features": "raw_window",
                },
            },
        )
