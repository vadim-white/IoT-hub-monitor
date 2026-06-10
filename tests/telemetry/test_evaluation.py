"""Юнит-тесты модуля оценки. Чистое ядро — без БД."""
import numpy as np

from iot_hub.apps.telemetry.ml.dataset import TimeSeries
from iot_hub.apps.telemetry.ml.evaluation import (
    point_metrics, per_type_recall, detection_latency, _segments,
)


def test_point_metrics_manual():
    y_true = np.array([False, True, True, False])
    y_pred = np.array([False, True, False, True])
    m = point_metrics(y_true, y_pred)
    assert (m.tp, m.fp, m.fn, m.tn) == (1, 1, 1, 1)
    assert m.precision == 0.5
    assert m.recall == 0.5
    assert m.f1 == 0.5
    assert m.false_alarm_rate == 0.5
    assert m.support_pos == 2
    assert m.n_evaluated == 4


def test_warmup_excluded():
    y_true = np.array([True, True, False, False])
    y_pred = np.array([True, False, True, False])
    warmup = np.array([True, False, False, False])  # первая точка — warmup
    m = point_metrics(y_true, y_pred, warmup)
    assert m.n_evaluated == 3            # первая исключена
    assert m.support_pos == 1            # из ground-truth осталась одна аномалия


def test_no_anomalies_no_crash():
    y_true = np.zeros(10, dtype=bool)
    y_pred = np.zeros(10, dtype=bool)
    m = point_metrics(y_true, y_pred)
    assert m.recall == 0.0
    assert m.precision == 0.0
    assert m.support_pos == 0


def test_per_type_recall():
    types = np.array(["", "spike", "spike", "", "stuck", "stuck"], dtype=object)
    labels = np.array([False, True, True, False, True, True])
    ts = TimeSeries(
        timestamps=np.datetime64("2025-01-01") + np.arange(6) * np.timedelta64(10, "m"),
        values=np.zeros(6),
        labels=labels,
        anomaly_types=types,
    )
    # поймали один spike из двух, оба stuck
    y_pred = np.array([False, True, False, False, True, True])
    rec = per_type_recall(ts, y_pred)
    assert rec["spike"] == 0.5
    assert rec["stuck"] == 1.0


def test_segments():
    labels = np.array([False, True, True, False, True, False])
    assert _segments(labels) == [(1, 3), (4, 5)]


def test_detection_latency():
    labels = np.array([False, True, True, True, False])  # один эпизод [1,4)
    ts = TimeSeries(
        timestamps=np.datetime64("2025-01-01") + np.arange(5) * np.timedelta64(10, "m"),
        values=np.zeros(5),
        labels=labels,
    )
    y_pred = np.array([False, False, True, False, False])  # сработал на 2-й точке эпизода
    lat = detection_latency(ts, y_pred)
    assert lat["episodes"] == 1
    assert lat["detected"] == 1
    assert lat["missed"] == 0
    assert lat["median_latency_points"] == 1.0  # offset от start=1 до сработки=2 → 1
