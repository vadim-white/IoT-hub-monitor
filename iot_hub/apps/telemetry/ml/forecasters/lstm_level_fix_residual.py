"""LSTM level-fix на остатке Holt-Winters — гибридный прогнозист (Фаза 4, инкр. 4).

Победитель диагностики Фазы 5 (`docs/experiments/06_lstm_diagnosis.md`, раунд 4):
HW даёт скелет (тренд+сезон, универсален на всех рядах), а LSTM учит ПРИРАЩЕНИЯ
остатка `r = y - hw.fittedvalues` относительно уровня окна (level-fix). Так
объединяем устойчивость классики с локальной адаптацией нейросети.

forecast = hw.forecast(h) + r_level + lstm_resid_increments * std

Внутренний HW — боевой `HoltWintersForecaster` (не дублируем statsmodels): на длинных
рядах разница heuristic/estimated-инициализации затухает, level-fix-эффект (−5…−13%
на TEMP-001/002) сохраняется. torch изолирован локально, как у `lstm.py` / автоэнкодера.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..dataset import TimeSeries
from ..forecast_base import Forecaster, ForecastResult, future_timestamps, infer_step
from ..persistence import ModelPersistenceMixin
from .holtwinters import HoltWintersForecaster


@dataclass
class LSTMLevelFixResidualForecaster(ModelPersistenceMixin, Forecaster):
    window: int = 144
    epochs: int = 100
    lr: float = 1e-3
    hidden: int = 32
    seasonal_periods: int = 144
    random_state: int = 42
    name: str = "lstm_lf_resid"
    # внутренний HW (боевой класс) — обучается в fit, его forecast = скелет прогноза
    _hw: HoltWintersForecaster = field(default=None, init=False, repr=False)
    # обученное состояние LSTM на остатке
    _model: object = field(default=None, init=False, repr=False)
    _resid: np.ndarray = field(default=None, init=False, repr=False)  # r = y - hw.fitted
    _std: float = field(default=None, init=False, repr=False)         # std остатка (нормировка)
    _r_level: float = field(default=None, init=False, repr=False)     # последний остаток r[-1]
    _tail: np.ndarray = field(default=None, init=False, repr=False)   # (r[-w:] - r_level)/std
    _last_ts: np.datetime64 = field(default=None, init=False, repr=False)
    _step: np.timedelta64 = field(default=None, init=False, repr=False)
    _horizon: int = field(default=None, init=False, repr=False)

    def fit(self, series: TimeSeries) -> "LSTMLevelFixResidualForecaster":
        import torch

        self._torch = torch
        # HW даёт тренд+сезон; остаток = то, что HW не объяснил (среднее≈0)
        self._hw = HoltWintersForecaster(seasonal_periods=self.seasonal_periods).fit(series)
        y = np.asarray(series.values, dtype=float)
        r = y - self._hw.fitted_values()   # публичный API HW (без приватного _fit)
        self._resid = r
        self._std = float(r.std()) + 1e-9
        self._r_level = float(r[-1])
        # хвост остатка относительно уровня окна (нормированный) — вход forecast
        self._tail = (r[-self.window:] - self._r_level) / self._std
        self._last_ts = series.timestamps[-1]
        self._step = infer_step(series.timestamps)
        # сеть строится лениво на первом forecast: выходной слой зависит от horizon
        return self

    def _build_and_train(self, horizon: int):
        from ..torch_utils import build_lstm_seq2seq, set_torch_determinism

        torch = self._torch
        # seed здесь, а не только в fit: после load() (без fit) ленивое обучение
        # сети должно быть так же детерминировано.
        set_torch_determinism(self.random_state)
        r, w, std = self._resid, self.window, self._std
        n = len(r)
        # окна остатка → приращения остатка на horizon вперёд, всё относительно
        # уровня r[t-1] (level-fix) и нормировано по std остатка
        X, D = [], []
        for t in range(w, n - horizon + 1):
            level = r[t - 1]
            X.append((r[t - w:t] - level) / std)
            D.append((r[t:t + horizon] - level) / std)
        if not X:
            # ряд короче окна+горизонта — fallback: только HW (без коррекции остатка)
            self._model = None
            return
        X = torch.tensor(np.array(X), dtype=torch.float32).unsqueeze(-1)  # (N, w, 1)
        D = torch.tensor(np.array(D), dtype=torch.float32)                 # (N, horizon)

        model = build_lstm_seq2seq(self.hidden, horizon)
        opt = torch.optim.Adam(model.parameters(), lr=self.lr)
        loss_fn = torch.nn.MSELoss()
        model.train()
        for _ in range(self.epochs):
            opt.zero_grad()
            loss = loss_fn(model(X), D)
            loss.backward()
            opt.step()
        model.eval()
        self._model = model

    def forecast(self, horizon: int) -> ForecastResult:
        torch = self._torch
        if self._model is None or self._horizon != horizon:
            self._horizon = horizon
            self._build_and_train(horizon)

        hw_fc = np.asarray(self._hw.forecast(horizon).mean, dtype=float)
        if self._model is None:
            # нет данных для обучения остатка → отдаём чистый HW
            mean = hw_fc
        else:
            x = torch.tensor(self._tail, dtype=torch.float32).reshape(1, self.window, 1)
            with torch.no_grad():
                d = self._model(x).numpy().ravel()
            # уровень остатка + предсказанные приращения (денормировка) + скелет HW
            resid_fc = self._r_level + d * self._std
            mean = hw_fc + resid_fc[:horizon]

        ts = future_timestamps(self._last_ts, self._step, horizon)
        return ForecastResult(
            timestamps=ts, mean=mean, lower=None, upper=None, horizon=horizon,
            meta={"method": self.name, "seasonal_periods": self.seasonal_periods,
                  "params": {"window": self.window, "epochs": self.epochs,
                             "hidden": self.hidden, "random_state": self.random_state}},
        )

    # --- персистентность: HW (.hw.joblib) + остаток/скаляры (.npz) + опц. веса (.pt) ---
    # Как у lstm.py: _model строится лениво на первом forecast (горизонт неизвестен на
    # fit). Сохраняем что есть; если сеть построена — кладём и веса. Внутренний HW
    # переиспользует свой _dump_state через отдельный stem-суффикс (другое расширение).
    def _dump_state(self, stem) -> None:
        if self._resid is None:
            raise ValueError("Нечего сохранять: вызовите fit() перед save()")
        from pathlib import Path

        stem = Path(stem)
        self._hw.save(stem.with_name(stem.name + "_hw"))  # → <stem>_hw.joblib + манифест
        has_model = self._model is not None
        np.savez(
            f"{stem}.npz",
            resid=self._resid, std=self._std, r_level=self._r_level, tail=self._tail,
            last_ts=self._last_ts, step=self._step,
            horizon=(self._horizon if has_model else -1),
            has_model=has_model,
        )
        if has_model:
            import torch

            torch.save(self._model.state_dict(), f"{stem}.pt")

    def _load_state(self, stem, manifest) -> None:
        import torch
        from pathlib import Path

        from ..torch_utils import build_lstm_seq2seq

        self._torch = torch  # нужен forecast(); fit() здесь не вызывался
        stem = Path(stem)
        # HW реконструируется из своего артефакта тем же гиперпараметром
        self._hw = HoltWintersForecaster(seasonal_periods=self.seasonal_periods).load(
            stem.with_name(stem.name + "_hw"))
        z = np.load(f"{stem}.npz", allow_pickle=False)
        self._resid = z["resid"]
        self._std = float(z["std"])
        self._r_level = float(z["r_level"])
        self._tail = z["tail"]
        self._last_ts = z["last_ts"][()]
        self._step = z["step"][()]
        if bool(z["has_model"]):
            self._horizon = int(z["horizon"])
            self._model = build_lstm_seq2seq(self.hidden, self._horizon)
            self._model.load_state_dict(torch.load(f"{stem}.pt", weights_only=True))
            self._model.eval()
