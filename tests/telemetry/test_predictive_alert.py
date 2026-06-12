"""Тесты предиктивного алерта. Чистый numpy, без БД, без гейтов."""
import numpy as np

from iot_hub.apps.telemetry.ml.forecast_base import ForecastResult
from iot_hub.apps.telemetry.ml.predictive_alert import predict_threshold_crossing


def _fc(mean, lower=None, upper=None):
    n = len(mean)
    ts = np.datetime64("2025-01-01") + np.arange(1, n + 1) * np.timedelta64(10, "m")
    return ForecastResult(timestamps=ts, mean=np.asarray(mean, float),
                          lower=lower, upper=upper, horizon=n, meta={})


def test_alert_fires_on_upward_drift():
    # прогноз растёт 30→39, upper=35 → пересечёт на индексе 6 (значение 36)
    mean = np.array([30, 31, 32, 33, 34, 35, 36, 37, 38, 39], dtype=float)
    c = predict_threshold_crossing(_fc(mean), lower_bound=None, upper_bound=35, step_minutes=10)
    assert c.will_cross
    assert c.bound_type == "upper"
    assert c.crossing_index == 6           # первое значение СТРОГО > 35 это 36 (индекс 6)
    assert c.lead_time_points == 7
    assert abs(c.lead_time_hours - 7 * 10 / 60) < 1e-9


def test_no_alert_within_bounds():
    mean = np.full(10, 20.0)
    c = predict_threshold_crossing(_fc(mean), lower_bound=10, upper_bound=30, step_minutes=10)
    assert not c.will_cross
    assert c.crossing_index is None


def test_lower_bound_crossing():
    mean = np.array([20, 18, 16, 14, 12, 10, 8], dtype=float)
    c = predict_threshold_crossing(_fc(mean), lower_bound=10, upper_bound=None, step_minutes=10)
    assert c.will_cross and c.bound_type == "lower"
    assert c.crossing_index == 6           # первое СТРОГО < 10 это 8 (индекс 6)


def test_lead_time_shrinks_closer_to_threshold():
    far = predict_threshold_crossing(_fc(np.arange(30.0, 40.0)), None, 35, 10)
    near = predict_threshold_crossing(_fc(np.arange(34.0, 44.0)), None, 35, 10)
    assert near.lead_time_points < far.lead_time_points


def test_interval_alerts_earlier():
    mean = np.array([30, 31, 32, 33, 34, 35, 36], dtype=float)
    upper = mean + 3.0   # верхняя граница интервала выше → пересечёт раньше
    point = predict_threshold_crossing(_fc(mean), None, 35, 10, use_interval=False)
    interval = predict_threshold_crossing(_fc(mean, upper=upper, lower=mean - 3),
                                          None, 35, 10, use_interval=True)
    assert interval.crossing_index <= point.crossing_index
    assert interval.confidence == "interval"


def test_interval_crossing_value_is_consistent():
    """crossing_value при use_interval берётся с границы интервала (не mean),
    иначе отчёт показал бы значение НЕ за порогом."""
    mean = np.array([30, 31, 32, 33, 34], dtype=float)
    upper = mean + 5.0   # upper: 35..39, mean внутри
    c = predict_threshold_crossing(_fc(mean, upper=upper, lower=mean - 5),
                                   None, 35.0, 10, use_interval=True)
    # значение в отчёте должно само быть > порога (с upper-границы), а не mean
    assert c.crossing_value > 35.0
    assert c.crossing_value == upper[c.crossing_index]
