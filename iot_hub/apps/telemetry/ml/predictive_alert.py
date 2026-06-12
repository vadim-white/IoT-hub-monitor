"""Предиктивный алерт — киллер-фича: прогноз × порог → когда метрика выйдет за предел.

Берёт ForecastResult и границы AlertThreshold, находит ПЕРВУЮ точку прогноза за
порогом в пределах горизонта и переводит её индекс во время («через ~6 часов»).
Чистый numpy, без Django — команда подставляет реальные lower/upper из БД.

Логика пересечения совпадает с AlertThreshold.check_threshold (devices/models.py):
value < lower_bound  или  value > upper_bound  (строгие неравенства).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .forecast_base import ForecastResult


@dataclass(frozen=True)
class ThresholdCrossing:
    will_cross: bool
    bound_type: str | None         # "upper" | "lower"
    crossing_index: int | None     # индекс в horizon (0-based)
    lead_time_points: int | None   # через сколько точек (= crossing_index + 1)
    lead_time_hours: float | None
    crossing_value: float | None
    crossing_timestamp: np.datetime64 | None
    confidence: str | None         # "point" | "interval"


def _first_crossing(values: np.ndarray, lower, upper) -> tuple[int | None, str | None]:
    for i, v in enumerate(values):
        if lower is not None and v < lower:
            return i, "lower"
        if upper is not None and v > upper:
            return i, "upper"
    return None, None


def predict_threshold_crossing(
    forecast: ForecastResult,
    lower_bound: float | None,
    upper_bound: float | None,
    step_minutes: float,
    use_interval: bool = False,
) -> ThresholdCrossing:
    """Первая точка прогноза, пересекающая порог в пределах horizon.

    use_interval=True и есть интервал → проверяем по границе интервала, ближней к
    порогу (upper-границу для верхнего порога, lower-границу для нижнего) — это даёт
    более ранний, консервативный алерт.
    """
    confidence = "point"
    upper_series = forecast.mean
    lower_series = forecast.mean
    if use_interval and forecast.upper is not None and forecast.lower is not None:
        upper_series = forecast.upper   # ближе к upper_bound → раньше сработает
        lower_series = forecast.lower   # ближе к lower_bound → раньше сработает
        confidence = "interval"

    # ищем раздельно по каждому порогу на соответствующей серии, берём раннее
    idx_u, _ = _first_crossing(upper_series, None, upper_bound)
    idx_l, _ = _first_crossing(lower_series, lower_bound, None)

    candidates = [(i, b) for i, b in ((idx_u, "upper"), (idx_l, "lower")) if i is not None]
    if not candidates:
        return ThresholdCrossing(False, None, None, None, None, None, None, confidence)

    crossing_index, bound_type = min(candidates, key=lambda c: c[0])
    lead_points = crossing_index + 1
    # значение берём с той серии, по которой нашли пересечение (mean для point,
    # upper/lower для interval) — иначе отчёт покажет значение, не за порогом
    decision_series = forecast.mean
    if confidence == "interval":
        decision_series = upper_series if bound_type == "upper" else lower_series
    return ThresholdCrossing(
        will_cross=True,
        bound_type=bound_type,
        crossing_index=crossing_index,
        lead_time_points=lead_points,
        lead_time_hours=lead_points * step_minutes / 60.0,
        crossing_value=float(decision_series[crossing_index]),
        crossing_timestamp=forecast.timestamps[crossing_index],
        confidence=confidence,
    )
