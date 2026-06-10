"""Тесты IsolationForestDetector. Требуют sklearn — пропускаются, если его нет
(напр. в .venv-analysis); целевой прогон в Docker."""
import numpy as np
import pytest

pytest.importorskip("sklearn")

from iot_hub.apps.telemetry.ml.dataset import TimeSeries
from iot_hub.apps.telemetry.ml.detectors.iforest import IsolationForestDetector
from iot_hub.apps.telemetry.ml.detectors.zscore import ZScoreDetector
from iot_hub.apps.telemetry.ml.evaluation import per_type_recall


def _series(values, types=None):
    n = len(values)
    ts = np.datetime64("2025-01-01") + np.arange(n) * np.timedelta64(10, "m")
    labels = None
    if types is not None:
        labels = np.array([bool(t) for t in types], dtype=bool)
        types = np.array(types, dtype=object)
    return TimeSeries(timestamps=ts, values=values.astype(float),
                      labels=labels, anomaly_types=types)


def _noisy(n=600, seed=0):
    return np.random.default_rng(seed).normal(50.0, 1.0, n)


def test_fits_interface():
    res = IsolationForestDetector(window=72).predict(_series(_noisy()))
    n = 600
    assert res.scores.shape == (n,)
    assert res.predictions.shape == (n,)
    assert res.warmup_mask.shape == (n,)


def test_deterministic():
    s = _series(_noisy())
    r1 = IsolationForestDetector(window=72, random_state=42).predict(s)
    r2 = IsolationForestDetector(window=72, random_state=42).predict(s)
    np.testing.assert_array_equal(r1.scores, r2.scores)
    np.testing.assert_array_equal(r1.predictions, r2.predictions)


def test_warmup_never_predicts():
    res = IsolationForestDetector(window=72).predict(_series(_noisy()))
    assert not res.predictions[:72].any()


def test_meta_has_threshold_key():
    """Команда читает meta['params']['threshold'] — он обязан существовать."""
    res = IsolationForestDetector(window=72).predict(_series(_noisy()))
    assert "threshold" in res.meta["params"]
    assert res.meta["method"] == "iforest"


def test_score_sign_on_spike():
    """В точке явного спайка score должен быть высоким (выше нуля)."""
    values = _noisy()
    values[400] += 12.0
    res = IsolationForestDetector(window=72).predict(_series(values))
    assert res.scores[400] > 0


def test_catches_dropout_better_than_zscore():
    """Главный научный тест: IF ловит пропадание сигнала (dropout) полностью,
    z-score — только края.

    Ряд: шумная норма ~50 + сегмент-провал в 0 (dropout). Провал — это плотный
    кластер значений ВНЕ нормального диапазона: IF изолирует его целиком, тогда
    как z-score реагирует только на резкие фронты входа/выхода (середина провала
    «плоская», его |z| мал относительно локального окна внутри нуля).
    """
    rng = np.random.default_rng(1)
    n = 1000
    values = rng.normal(50.0, 1.0, n)
    types = [""] * n
    values[500:510] = 0.0
    for i in range(500, 510):
        types[i] = "dropout"
    s = _series(values, types)

    if_pred = IsolationForestDetector(window=24, contamination=0.03).predict(s)
    zs_pred = ZScoreDetector(window=24, threshold=3.0).predict(s)

    if_recall = per_type_recall(s, if_pred.predictions, if_pred.warmup_mask).get("dropout", 0.0)
    zs_recall = per_type_recall(s, zs_pred.predictions, zs_pred.warmup_mask).get("dropout", 0.0)

    assert if_recall > zs_recall, "IF должен ловить dropout лучше z-score"
    assert if_recall >= 0.9, "IF должен поймать почти весь dropout-сегмент"
