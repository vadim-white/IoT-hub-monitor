"""Базовая абстракция прогнозирования временных рядов.

Параллель к base.py (детекция), но ДРУГАЯ задача: forecasting предсказывает
будущие значения ряда, а не скорит точку на аномальность. Поэтому Forecaster —
самостоятельный интерфейс, не наследник AnomalyDetector.

Ключевое для научной честности: forecast(horizon) НЕ получает ряд-аргумент —
прогноз продолжает обучающий ряд из fit. Forecaster физически не видит будущее,
что структурно исключает look-ahead при backtesting.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import numpy as np

from .dataset import TimeSeries


@dataclass(frozen=True)
class ForecastResult:
    """Прогноз на horizon точек вперёд от конца обучающего ряда.

    timestamps — datetime64[ns] (horizon,): метки будущих точек (шаг = шаг ряда)
    mean       — float64 (horizon,): точечный прогноз
    lower/upper — float64 (horizon,) | None: границы интервала (для предиктивного алерта)
    horizon    — int
    meta       — {"method", "seasonal_periods", "params"}
    """
    timestamps: np.ndarray
    mean: np.ndarray
    lower: np.ndarray | None
    upper: np.ndarray | None
    horizon: int
    meta: dict = field(default_factory=dict)


class Forecaster(ABC):
    """Интерфейс прогнозирования. Реализуют naive / holtwinters / lstm."""
    name: str = "base"

    @abstractmethod
    def fit(self, series: TimeSeries) -> "Forecaster":
        """Обучение на истории. Сохраняет шаг времени для генерации будущих меток."""

    @abstractmethod
    def forecast(self, horizon: int) -> ForecastResult:
        """Прогноз следующих horizon точек ПОСЛЕ конца обучающего ряда.
        Использует только данные из fit (causal по построению)."""


def future_timestamps(last_ts: np.datetime64, step: np.timedelta64, horizon: int) -> np.ndarray:
    """horizon будущих меток после last_ts с заданным шагом."""
    return last_ts + step * np.arange(1, horizon + 1)


def infer_step(timestamps: np.ndarray) -> np.timedelta64:
    """Шаг ряда = медиана разностей соседних меток (устойчиво к пропускам)."""
    diffs = np.diff(timestamps)
    return np.median(diffs.astype("timedelta64[s]")).astype("timedelta64[s]")
