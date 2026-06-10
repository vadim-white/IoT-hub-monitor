"""Базовая абстракция детектора аномалий.

Все методы (z-score сейчас; Isolation Forest, автоэнкодер — позже) реализуют
один интерфейс AnomalyDetector и возвращают единый DetectionResult. Благодаря
этому management-команда и модуль оценки не зависят от конкретного метода —
новый детектор добавляется без их изменения.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import numpy as np

from .dataset import TimeSeries


@dataclass(frozen=True)
class DetectionResult:
    """Результат детекции по ряду.

    scores      — anomaly score на точку (больше = аномальнее)
    predictions — bool (n,): score прошёл порог и точка вне warmup
    warmup_mask — bool (n,): True там, где детектор «не прогрет» (нет полного окна).
                  Эти точки исключаются из метрик честно и единообразно для всех методов.
    threshold   — фактический порог решения
    meta        — {"method", "window", "params"} для самоописываемого отчёта
    """
    scores: np.ndarray
    predictions: np.ndarray
    warmup_mask: np.ndarray
    threshold: float
    meta: dict = field(default_factory=dict)


class AnomalyDetector(ABC):
    """Интерфейс детектора. fit/score/predict — точка расширения для IF/AE.

    Для z-score fit — no-op (метод онлайновый). Для обучаемых методов fit
    калибрует модель, score возвращает anomaly score, predict бинаризует по порогу.
    """
    name: str = "base"

    def fit(self, series: TimeSeries) -> "AnomalyDetector":
        return self

    @abstractmethod
    def score(self, series: TimeSeries) -> np.ndarray:
        """Anomaly score на каждую точку. Семантика: больше = аномальнее."""

    @abstractmethod
    def predict(self, series: TimeSeries) -> DetectionResult:
        """score + бинаризация по порогу + warmup_mask."""
