"""Контейнер временного ряда для ML-детекторов — чистый numpy, без Django.

Граница между ORM-слоем и ML-ядром: management-команда (или будущая Celery-задача)
извлекает телеметрию из БД, собирает TimeSeries и передаёт его детектору. Само
ядро про Django не знает — это даёт тестируемость без БД и переиспользование
в офлайн-экспериментах диплома.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class TimeSeries:
    """Один ряд одной метрики одного устройства.

    timestamps    — datetime64[ns], строго по возрастанию (rolling требует хронологии)
    values        — float64 (n,)
    labels        — bool ground-truth (n,) либо None, если меток нет
    anomaly_types — str per-point ("" для нормы) либо None; нужен для per-type метрик
    """
    timestamps: np.ndarray
    values: np.ndarray
    labels: np.ndarray | None = None
    anomaly_types: np.ndarray | None = None

    def __post_init__(self):
        n = len(self.values)
        if len(self.timestamps) != n:
            raise ValueError("timestamps и values должны быть одной длины")
        if self.labels is not None and len(self.labels) != n:
            raise ValueError("labels должны быть длины values")
        if self.anomaly_types is not None and len(self.anomaly_types) != n:
            raise ValueError("anomaly_types должны быть длины values")

    def __len__(self) -> int:
        return len(self.values)
