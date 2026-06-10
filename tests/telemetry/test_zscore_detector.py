"""Юнит-тесты ZScoreDetector. Чистое ядро — без БД, без @django_db."""
import numpy as np
import pytest

from iot_hub.apps.telemetry.ml.dataset import TimeSeries
from iot_hub.apps.telemetry.ml.detectors.zscore import ZScoreDetector


def _series(values: np.ndarray) -> TimeSeries:
    n = len(values)
    ts = np.datetime64("2025-01-01") + np.arange(n) * np.timedelta64(10, "m")
    return TimeSeries(timestamps=ts, values=values.astype(float))


def _noisy_constant(n=200, mean=50.0, std=1.0, seed=0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.normal(mean, std, n)


def test_detects_spike():
    values = _noisy_constant()
    values[150] += 10.0  # выброс +10σ
    det = ZScoreDetector(window=24, threshold=3.0)
    res = det.predict(_series(values))
    assert res.predictions[150], "спайк должен быть пойман"
    # ложных срабатываний почти нет на чистом шуме
    assert res.predictions.sum() <= 3


def test_warmup_never_predicts():
    values = _noisy_constant()
    det = ZScoreDetector(window=24, threshold=3.0)
    res = det.predict(_series(values))
    assert res.warmup_mask[:24].all()
    assert not res.predictions[:24].any()


def test_constant_series_no_crash():
    """stuck/dropout: std=0 не вызывает inf/nan и не падает."""
    values = np.full(100, 42.0)
    det = ZScoreDetector(window=24, threshold=3.0)
    res = det.predict(_series(values))
    assert np.isfinite(res.scores).all()
    assert not res.predictions.any()


def test_trailing_causality():
    """Спайк в точке t не влияет на score левее t (нет look-ahead)."""
    values = _noisy_constant()
    det = ZScoreDetector(window=24, threshold=3.0)
    base = det.score(_series(values.copy()))
    spiked = values.copy()
    spiked[150] += 10.0
    after = det.score(_series(spiked))
    np.testing.assert_array_equal(base[:150], after[:150])


def test_deterministic():
    values = _noisy_constant()
    det = ZScoreDetector(window=24, threshold=3.0)
    r1 = det.predict(_series(values))
    r2 = det.predict(_series(values))
    np.testing.assert_array_equal(r1.scores, r2.scores)
    np.testing.assert_array_equal(r1.predictions, r2.predictions)


def test_lower_threshold_more_recall():
    values = _noisy_constant()
    values[150] += 5.0
    s = _series(values)
    loose = ZScoreDetector(window=24, threshold=2.0).predict(s).predictions.sum()
    strict = ZScoreDetector(window=24, threshold=4.0).predict(s).predictions.sum()
    assert loose >= strict


def test_meta_is_self_describing():
    res = ZScoreDetector(window=36, threshold=2.5).predict(_series(_noisy_constant()))
    assert res.meta["method"] == "zscore"
    assert res.meta["window"] == 36
    assert res.threshold == 2.5
