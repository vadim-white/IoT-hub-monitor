"""Наивный прогноз — обязательный baseline (как z-score для детекции).

Seasonal-naive: ŷ[t+h] = y[t+h-S], где S — период сезонности (суточный = 144
точки при шаге 10 мин). При S=0 вырождается в last-value naive (ŷ=y[последнее]).

Last-value наивно повторяет последнее значение и проваливается на сезонном ряде —
именно это показывает, что суточный ход игнорировать нельзя. Seasonal-naive чинит
и сам становится сильным baseline, который «умным» методам надо обойти.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..dataset import TimeSeries
from ..forecast_base import Forecaster, ForecastResult, future_timestamps, infer_step
from ..persistence import ModelPersistenceMixin


@dataclass
class SeasonalNaiveForecaster(ModelPersistenceMixin, Forecaster):
    seasonal_periods: int = 144   # суточный период при шаге 10 мин; 0 → last-value
    name: str = "naive"
    _values: np.ndarray = field(default=None, init=False, repr=False)
    _last_ts: np.datetime64 = field(default=None, init=False, repr=False)
    _step: np.timedelta64 = field(default=None, init=False, repr=False)

    def fit(self, series: TimeSeries) -> "SeasonalNaiveForecaster":
        self._values = np.asarray(series.values, dtype=float)
        self._last_ts = series.timestamps[-1]
        self._step = infer_step(series.timestamps)
        return self

    def forecast(self, horizon: int) -> ForecastResult:
        x = self._values
        n = len(x)
        S = self.seasonal_periods
        mean = np.empty(horizon, dtype=float)
        if S and n >= S:
            # ŷ[t+h] = последнее наблюдённое значение той же фазы сезона
            for h in range(horizon):
                mean[h] = x[n - S + (h % S)]
        else:
            mean[:] = x[-1]   # last-value
        ts = future_timestamps(self._last_ts, self._step, horizon)
        return ForecastResult(
            timestamps=ts, mean=mean, lower=None, upper=None, horizon=horizon,
            meta={"method": self.name, "seasonal_periods": S, "params": {}},
        )

    # --- персистентность: чистый numpy через .npz ---
    def _dump_state(self, stem) -> None:
        if self._values is None:
            raise ValueError("Нечего сохранять: вызовите fit() перед save()")
        np.savez(
            f"{stem}.npz",
            values=self._values, last_ts=self._last_ts, step=self._step,
        )

    def _load_state(self, stem, manifest) -> None:
        z = np.load(f"{stem}.npz", allow_pickle=False)
        self._values = z["values"]
        self._last_ts = z["last_ts"][()]   # 0-d → datetime64 скаляр
        self._step = z["step"][()]
