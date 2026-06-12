"""Тесты бэктеста прогнозов. Чистый numpy, без БД, без гейтов."""
import numpy as np

from iot_hub.apps.telemetry.ml.dataset import TimeSeries
from iot_hub.apps.telemetry.ml.forecasters.naive import SeasonalNaiveForecaster
from iot_hub.apps.telemetry.ml.forecast_evaluation import (
    forecast_point_metrics, rolling_origin_backtest,
)


def _series(values: np.ndarray) -> TimeSeries:
    n = len(values)
    ts = np.datetime64("2025-01-01") + np.arange(n) * np.timedelta64(10, "m")
    return TimeSeries(timestamps=ts, values=values.astype(float))


def _sine(n=1000, period=24):
    return 50 + 5 * np.sin(2 * np.pi * np.arange(n) / period)


def test_point_metrics_manual():
    mae, rmse, mape = forecast_point_metrics([1, 2, 3], [1, 2, 5])
    assert mae == (0 + 0 + 2) / 3
    assert abs(rmse - np.sqrt((0 + 0 + 4) / 3)) < 1e-9


def test_backtest_runs():
    s = _series(_sine(n=600, period=24))
    res = rolling_origin_backtest(
        lambda: SeasonalNaiveForecaster(seasonal_periods=24),
        s, horizon=24, initial_train=100, step=50)
    assert res["n_origins"] > 0
    assert res["mae"] is not None


def test_backtest_no_future_leakage():
    """Изменение ряда ПОСЛЕ последнего нужного индекса не меняет метрики backtest —
    forecaster не подглядывает в будущее (аналог causality-теста детекции)."""
    base = _sine(n=500, period=24)
    s1 = _series(base.copy())

    factory = lambda: SeasonalNaiveForecaster(seasonal_periods=24)
    initial_train, horizon, step, max_origins = 100, 24, 50, 3
    res1 = rolling_origin_backtest(factory, s1, horizon, initial_train, step, max_origins)

    # последний использованный индекс = последний origin + horizon
    last_origin = initial_train + step * (res1["n_origins"] - 1)
    last_used = last_origin + horizon
    mutated = base.copy()
    mutated[last_used:] += 1000.0   # портим хвост ЗА пределами использованного
    res2 = rolling_origin_backtest(factory, _series(mutated), horizon, initial_train, step, max_origins)

    assert res1["mae"] == res2["mae"]
    assert res1["n_origins"] == res2["n_origins"]


def test_backtest_too_short_returns_zero_origins():
    s = _series(_sine(n=120, period=24))
    res = rolling_origin_backtest(
        lambda: SeasonalNaiveForecaster(seasonal_periods=24),
        s, horizon=24, initial_train=200, step=50)  # initial_train > len
    assert res["n_origins"] == 0
    assert res["mae"] is None
