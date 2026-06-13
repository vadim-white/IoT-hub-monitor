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
from ..persistence import ModelPersistenceMixin


def _build_net(hidden: int, horizon: int):
    """Сеть LSTM→Linear на уровне модуля — чтобы её можно было реконструировать
    при load (state_dict требует тот же класс). torch импортируется локально."""
    from torch import nn

    class Net(nn.Module):
        def __init__(self, hidden, horizon):
            super().__init__()
            self.lstm = nn.LSTM(1, hidden, batch_first=True)
            self.head = nn.Linear(hidden, horizon)

        def forward(self, x):
            out, _ = self.lstm(x)
            return self.head(out[:, -1, :])

    return Net(hidden, horizon)


@dataclass
class LSTMForecaster(ModelPersistenceMixin, Forecaster):
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
        return self

    def _build_and_train(self, horizon: int):
        from ..torch_utils import set_torch_determinism

        torch = self._torch
        # seed здесь, а не только в fit: после load() (без fit) ленивое обучение
        # сети должно быть так же детерминировано.
        set_torch_determinism(self.random_state)
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

        model = _build_net(self.hidden, horizon)
        opt = torch.optim.Adam(model.parameters(), lr=self.lr)
        loss_fn = torch.nn.MSELoss()
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

    # --- персистентность: pre-fit состояние (.npz) + опц. веса сети (.pt) ---
    # Особый случай: _model строится лениво на первом forecast (горизонт неизвестен
    # на fit). Сохраняем то, что есть; если сеть уже построена — кладём и её веса.
    def _dump_state(self, stem) -> None:
        if self._yn is None:
            raise ValueError("Нечего сохранять: вызовите fit() перед save()")
        has_model = self._model is not None
        np.savez(
            f"{stem}.npz",
            mean=self._mean, std=self._std, tail=self._tail, yn=self._yn,
            last_ts=self._last_ts, step=self._step,
            horizon=(self._horizon if has_model else -1),
            has_model=has_model,
        )
        if has_model:
            import torch

            torch.save(self._model.state_dict(), f"{stem}.pt")

    def _load_state(self, stem, manifest) -> None:
        import torch

        self._torch = torch  # нужен forecast(); fit() здесь не вызывался
        z = np.load(f"{stem}.npz", allow_pickle=False)
        self._mean = float(z["mean"])
        self._std = float(z["std"])
        self._tail = z["tail"]
        self._yn = z["yn"]
        self._last_ts = z["last_ts"][()]
        self._step = z["step"][()]
        if bool(z["has_model"]):
            self._horizon = int(z["horizon"])
            self._model = _build_net(self.hidden, self._horizon)
            self._model.load_state_dict(torch.load(f"{stem}.pt"))
            self._model.eval()
