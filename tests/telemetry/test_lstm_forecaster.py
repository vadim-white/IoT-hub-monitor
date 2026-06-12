"""Тесты LSTMForecaster. Требуют torch — пропускаются без него."""
import numpy as np
import pytest

pytest.importorskip("torch")

from iot_hub.apps.telemetry.ml.dataset import TimeSeries
from iot_hub.apps.telemetry.ml.forecasters.lstm import LSTMForecaster


def _series(values: np.ndarray) -> TimeSeries:
    n = len(values)
    ts = np.datetime64("2025-01-01") + np.arange(n) * np.timedelta64(10, "m")
    return TimeSeries(timestamps=ts, values=values.astype(float))


def _sine(n=600, period=24):
    return 50 + 5 * np.sin(2 * np.pi * np.arange(n) / period)


def test_fits_interface():
    fc = LSTMForecaster(window=48, epochs=5).fit(_series(_sine())).forecast(12)
    assert fc.mean.shape == (12,)
    assert fc.horizon == 12
    assert fc.meta["method"] == "lstm"


def test_deterministic():
    s = _series(_sine())
    r1 = LSTMForecaster(window=48, epochs=5, random_state=42).fit(s).forecast(12)
    r2 = LSTMForecaster(window=48, epochs=5, random_state=42).fit(s).forecast(12)
    np.testing.assert_allclose(r1.mean, r2.mean)


def test_timestamps_continue():
    s = _series(_sine())
    fc = LSTMForecaster(window=48, epochs=5).fit(s).forecast(6)
    assert fc.timestamps[0] == s.timestamps[-1] + np.timedelta64(10, "m")
    assert len(fc.timestamps) == 6
