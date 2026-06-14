"""Тесты HoltWintersForecaster. Требуют statsmodels — пропускаются без него."""
import numpy as np
import pytest

pytest.importorskip("statsmodels")

from iot_hub.apps.telemetry.ml.dataset import TimeSeries
from iot_hub.apps.telemetry.ml.forecasters.holtwinters import HoltWintersForecaster
from iot_hub.apps.telemetry.ml.forecasters.naive import SeasonalNaiveForecaster
from iot_hub.apps.telemetry.ml.forecast_evaluation import forecast_point_metrics


def _series(values: np.ndarray) -> TimeSeries:
    n = len(values)
    ts = np.datetime64("2025-01-01") + np.arange(n) * np.timedelta64(10, "m")
    return TimeSeries(timestamps=ts, values=values.astype(float))


def test_captures_trend():
    """На линейном тренде Holt-Winters продолжает тренд (MAE << last-value naive)."""
    n = 300
    values = np.linspace(0, 100, n)  # чистый рост
    train = _series(values[:250])
    truth = values[250:250 + 24]

    hw = HoltWintersForecaster(seasonal_periods=24).fit(train).forecast(24)
    naive = SeasonalNaiveForecaster(seasonal_periods=0).fit(train).forecast(24)

    mae_hw, _, _ = forecast_point_metrics(truth, hw.mean)
    mae_naive, _, _ = forecast_point_metrics(truth, naive.mean)
    assert mae_hw < mae_naive   # HW видит тренд, last-value застывает


def test_interval_present():
    values = 50 + 5 * np.sin(2 * np.pi * np.arange(200) / 24)
    fc = HoltWintersForecaster(seasonal_periods=24).fit(_series(values)).forecast(12)
    assert fc.lower is not None and fc.upper is not None
    assert np.all(fc.lower <= fc.mean) and np.all(fc.mean <= fc.upper)


def test_deterministic():
    values = 50 + 5 * np.sin(2 * np.pi * np.arange(200) / 24) + np.arange(200) * 0.05
    s = _series(values)
    r1 = HoltWintersForecaster(seasonal_periods=24).fit(s).forecast(12)
    r2 = HoltWintersForecaster(seasonal_periods=24).fit(s).forecast(12)
    np.testing.assert_allclose(r1.mean, r2.mean)


def test_fitted_values_length():
    """fitted_values() (публичный API для гибридов) той же длины, что обучающий ряд."""
    values = 50 + 5 * np.sin(2 * np.pi * np.arange(200) / 24) + np.arange(200) * 0.05
    s = _series(values)
    hw = HoltWintersForecaster(seasonal_periods=24).fit(s)
    fitted = hw.fitted_values()
    assert fitted.shape == (200,)
    # остаток (то, на чём учится lstm_lf_resid) имеет ~нулевое среднее
    assert abs(float((values - fitted).mean())) < 1.0
