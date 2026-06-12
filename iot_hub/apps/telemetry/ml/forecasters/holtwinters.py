"""Holt-Winters (экспоненциальное сглаживание) — классический метод с трендом и сезонностью.

statsmodels ExponentialSmoothing с аддитивным трендом и аддитивной сезонностью.
Тренд нужен для прогноза дрейфа к порогу, сезонность — для суточного хода.
Интервал — эмпирический по std остатков обучения (надёжнее капризного API интервалов).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..dataset import TimeSeries
from ..forecast_base import Forecaster, ForecastResult, future_timestamps, infer_step


@dataclass
class HoltWintersForecaster(Forecaster):
    seasonal_periods: int = 144
    trend: str = "add"
    seasonal: str = "add"
    z: float = 1.96               # ширина интервала (95%)
    name: str = "holtwinters"
    _fit: object = field(default=None, init=False, repr=False)
    _last_ts: np.datetime64 = field(default=None, init=False, repr=False)
    _step: np.timedelta64 = field(default=None, init=False, repr=False)
    _resid_std: float = field(default=None, init=False, repr=False)

    def fit(self, series: TimeSeries) -> "HoltWintersForecaster":
        from statsmodels.tsa.holtwinters import ExponentialSmoothing

        y = np.asarray(series.values, dtype=float)
        # сезонность включаем только если есть >=2 полных периода
        seasonal = self.seasonal if len(y) >= 2 * self.seasonal_periods else None
        periods = self.seasonal_periods if seasonal else None
        model = ExponentialSmoothing(
            y, trend=self.trend, seasonal=seasonal, seasonal_periods=periods,
            initialization_method="heuristic")
        self._fit = model.fit()
        self._resid_std = float(np.std(self._fit.resid)) if self._fit.resid is not None else 0.0
        self._last_ts = series.timestamps[-1]
        self._step = infer_step(series.timestamps)
        return self

    def forecast(self, horizon: int) -> ForecastResult:
        mean = np.asarray(self._fit.forecast(horizon), dtype=float)
        band = self.z * self._resid_std
        ts = future_timestamps(self._last_ts, self._step, horizon)
        return ForecastResult(
            timestamps=ts, mean=mean,
            lower=mean - band, upper=mean + band,
            horizon=horizon,
            meta={"method": self.name, "seasonal_periods": self.seasonal_periods,
                  "params": {"trend": self.trend, "seasonal": self.seasonal}},
        )
