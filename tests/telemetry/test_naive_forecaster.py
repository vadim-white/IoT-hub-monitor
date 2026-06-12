"""Тесты SeasonalNaiveForecaster. Чистый numpy, без БД, без гейтов."""
import numpy as np

from iot_hub.apps.telemetry.ml.dataset import TimeSeries
from iot_hub.apps.telemetry.ml.forecasters.naive import SeasonalNaiveForecaster


def _series(values: np.ndarray) -> TimeSeries:
    n = len(values)
    ts = np.datetime64("2025-01-01") + np.arange(n) * np.timedelta64(10, "m")
    return TimeSeries(timestamps=ts, values=values.astype(float))


def test_seasonal_naive_repeats_period():
    """На чистом периодическом ряде прогноз = значения прошлого периода (MAE≈0)."""
    period = 24
    t = np.arange(10 * period)
    values = 50 + 5 * np.sin(2 * np.pi * t / period)
    s = _series(values)
    fc = SeasonalNaiveForecaster(seasonal_periods=period).fit(s).forecast(period)
    # будущее продолжает синус: сравним с аналитическим продолжением
    future = 50 + 5 * np.sin(2 * np.pi * np.arange(len(values), len(values) + period) / period)
    assert np.abs(fc.mean - future).mean() < 1e-9


def test_last_value_when_no_season():
    """S=0 → прогноз постоянен и равен последнему значению."""
    values = np.arange(100.0)
    fc = SeasonalNaiveForecaster(seasonal_periods=0).fit(_series(values)).forecast(10)
    assert np.all(fc.mean == 99.0)


def test_timestamps_continue_series():
    values = np.arange(50.0)
    s = _series(values)
    fc = SeasonalNaiveForecaster(seasonal_periods=24).fit(s).forecast(5)
    # первая будущая метка = последняя + шаг
    assert fc.timestamps[0] == s.timestamps[-1] + np.timedelta64(10, "m")
    assert len(fc.timestamps) == 5


def test_result_shapes():
    fc = SeasonalNaiveForecaster(seasonal_periods=24).fit(_series(np.arange(60.0))).forecast(12)
    assert fc.mean.shape == (12,)
    assert fc.horizon == 12
    assert fc.meta["method"] == "naive"
