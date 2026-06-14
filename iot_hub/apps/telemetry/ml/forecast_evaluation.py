"""Оценка прогнозов — чистый numpy, без Django. НЕ трогает evaluation.py (детекция).

Rolling-origin (walk-forward) backtest: на каждом origin t обучаем НА ПРОШЛОМ
(series[:t]), прогнозируем horizon точек, сравниваем с реальными series[t:t+horizon].
Метрики усредняются по origin'ам.

Главная защита от утечки будущего: на каждый origin создаётся СВЕЖИЙ forecaster
(factory), обучаемый строго на срезе series[:t]. Forecaster по контракту не получает
будущее. Тест test_backtest_no_future_leakage проверяет это мутацией хвоста ряда.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .dataset import TimeSeries


@dataclass(frozen=True)
class ForecastMetrics:
    mae: float
    rmse: float
    mape: float          # sMAPE-подобный с epsilon-флором (защита от деления на ~0)
    horizon: int
    n_origins: int


def forecast_point_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> tuple[float, float, float]:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    err = y_pred - y_true
    mae = float(np.abs(err).mean())
    rmse = float(np.sqrt((err ** 2).mean()))
    # sMAPE: |err| / ((|true|+|pred|)/2), устойчив около нуля
    denom = (np.abs(y_true) + np.abs(y_pred)) / 2.0
    mape = float((np.abs(err) / np.maximum(denom, 1e-9)).mean() * 100.0)
    return mae, rmse, mape


def slice_series(series: TimeSeries, end: int) -> TimeSeries:
    """Срез series[:end] — ТОЛЬКО прошлое относительно origin/точки отсечения."""
    return TimeSeries(
        timestamps=series.timestamps[:end],
        values=series.values[:end],
        labels=None if series.labels is None else series.labels[:end],
        anomaly_types=None if series.anomaly_types is None else series.anomaly_types[:end],
    )


# обратная совместимость для внутреннего вызова в rolling_origin_backtest
_slice_series = slice_series


def rolling_origin_backtest(
    forecaster_factory,
    series: TimeSeries,
    horizon: int,
    initial_train: int,
    step: int = 144,
    max_origins: int | None = None,
) -> dict:
    """Walk-forward бэктест. forecaster_factory() — Callable, дающий СВЕЖИЙ forecaster.

    Возвращает {"mae","rmse","mape","n_origins","horizon"} — агрегаты по origin'ам.
    Origin'ы: t = initial_train, initial_train+step, ... пока t+horizon <= len(series).
    """
    n = len(series.values)
    maes, rmses, mapes = [], [], []
    t = initial_train
    while t + horizon <= n:
        train = _slice_series(series, t)
        fc = forecaster_factory().fit(train).forecast(horizon)
        truth = series.values[t:t + horizon]
        mae, rmse, mape = forecast_point_metrics(truth, fc.mean)
        maes.append(mae); rmses.append(rmse); mapes.append(mape)
        if max_origins and len(maes) >= max_origins:
            break
        t += step
    if not maes:
        return {"mae": None, "rmse": None, "mape": None, "n_origins": 0, "horizon": horizon}
    return {
        "mae": float(np.mean(maes)),
        "rmse": float(np.mean(rmses)),
        "mape": float(np.mean(mapes)),
        "n_origins": len(maes),
        "horizon": horizon,
    }
