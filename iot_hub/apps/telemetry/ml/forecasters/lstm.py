"""LSTM-прогнозист (torch) — нейросетевой метод для сравнения.

Учит по каузальным окнам предсказывать следующие horizon точек (direct multi-step:
один проход выдаёт весь горизонт). Стандартизация по статистикам train (без утечки).
torch изолирован здесь и в torch_utils, как у автоэнкодера.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..dataset import TimeSeries
from ..forecast_base import Forecaster, ForecastResult, future_timestamps, infer_step


@dataclass
class LSTMForecaster(Forecaster):
    window: int = 144
    epochs: int = 100
    lr: float = 1e-3
    hidden: int = 32
    random_state: int = 42
    name: str = "lstm"
    _model: object = field(default=None, init=False, repr=False)
    _mean: float = field(default=None, init=False, repr=False)
    _std: float = field(default=None, init=False, repr=False)
    _tail: np.ndarray = field(default=None, init=False, repr=False)
    _last_ts: np.datetime64 = field(default=None, init=False, repr=False)
    _step: np.timedelta64 = field(default=None, init=False, repr=False)
    _horizon: int = field(default=None, init=False, repr=False)

    def fit(self, series: TimeSeries) -> "LSTMForecaster":
        import torch
        from torch import nn
        from ..torch_utils import set_torch_determinism

        set_torch_determinism(self.random_state)
        y = np.asarray(series.values, dtype=float)
        self._mean, self._std = float(y.mean()), float(y.std()) + 1e-9
        yn = (y - self._mean) / self._std
        self._tail = yn[-self.window:].copy()
        self._last_ts = series.timestamps[-1]
        self._step = infer_step(series.timestamps)
        # horizon фиксируется при первом forecast; модель строится лениво там,
        # т.к. выходной слой зависит от horizon (direct multi-step)
        self._yn = yn
        self._torch = torch
        self._nn = nn
        return self

    def _build_and_train(self, horizon: int):
        torch, nn = self._torch, self._nn
        yn, w = self._yn, self.window
        n = len(yn)
        # окна (X) → следующие horizon точек (Y)
        X, Y = [], []
        for t in range(w, n - horizon + 1):
            X.append(yn[t - w:t])
            Y.append(yn[t:t + horizon])
        if not X:
            # ряд короче окна+горизонта — fallback на повтор последнего
            self._model = None
            return
        X = torch.tensor(np.array(X), dtype=torch.float32).unsqueeze(-1)  # (N, w, 1)
        Y = torch.tensor(np.array(Y), dtype=torch.float32)

        class Net(nn.Module):
            def __init__(self, hidden, horizon):
                super().__init__()
                self.lstm = nn.LSTM(1, hidden, batch_first=True)
                self.head = nn.Linear(hidden, horizon)

            def forward(self, x):
                out, _ = self.lstm(x)
                return self.head(out[:, -1, :])

        model = Net(self.hidden, horizon)
        opt = torch.optim.Adam(model.parameters(), lr=self.lr)
        loss_fn = nn.MSELoss()
        model.train()
        for _ in range(self.epochs):
            opt.zero_grad()
            loss = loss_fn(model(X), Y)
            loss.backward()
            opt.step()
        model.eval()
        self._model = model

    def forecast(self, horizon: int) -> ForecastResult:
        torch = self._torch
        if self._model is None or self._horizon != horizon:
            self._horizon = horizon
            self._build_and_train(horizon)

        if self._model is None:
            mean = np.full(horizon, self._tail[-1] * self._std + self._mean)
        else:
            x = torch.tensor(self._tail, dtype=torch.float32).reshape(1, self.window, 1)
            with torch.no_grad():
                pred = self._model(x).numpy().ravel()
            mean = pred * self._std + self._mean

        ts = future_timestamps(self._last_ts, self._step, horizon)
        return ForecastResult(
            timestamps=ts, mean=mean, lower=None, upper=None, horizon=horizon,
            meta={"method": self.name, "seasonal_periods": None,
                  "params": {"window": self.window, "epochs": self.epochs,
                             "hidden": self.hidden, "random_state": self.random_state}},
        )
