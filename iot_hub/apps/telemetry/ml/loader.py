"""Мост ORM → TimeSeries. Единственное место, где ML-слой касается Django.

Вынесен отдельной функцией, чтобы и management-команда detect_anomalies, и
будущая Celery-задача периодического скоринга использовали один загрузчик без
дублирования. Само ядро ml/ остаётся независимым от Django.
"""
from __future__ import annotations

import numpy as np
from django.utils import timezone

from iot_hub.apps.telemetry.models import Telemetry
from .dataset import TimeSeries


def load_series(device, metric, days: int | None = None) -> TimeSeries:
    """Собирает TimeSeries по (device, metric) из БД, строго по возрастанию времени.

    Ground-truth и тип аномалии извлекаются из Telemetry.raw_data['anomaly'].
    Если меток нет (не synthetic-данные) — labels/anomaly_types заполняются как
    «нормальные», метрики тогда не имеют смысла, но детекция отработает.
    """
    qs = Telemetry.objects.filter(device=device, metric=metric)
    if days:
        qs = qs.filter(recorded_at__gte=timezone.now() - timezone.timedelta(days=days))
    qs = qs.order_by("recorded_at")

    values: list[float] = []
    timestamps: list = []
    labels: list[bool] = []
    types: list[str] = []
    for value, recorded_at, raw_data in qs.values_list("value", "recorded_at", "raw_data"):
        values.append(value)
        timestamps.append(np.datetime64(recorded_at.replace(tzinfo=None)))
        anomaly = (raw_data or {}).get("anomaly", {})
        labels.append(bool(anomaly.get("is_anomaly", False)))
        types.append(anomaly.get("type", "") if anomaly.get("is_anomaly") else "")

    return TimeSeries(
        timestamps=np.array(timestamps, dtype="datetime64[ns]"),
        values=np.array(values, dtype=float),
        labels=np.array(labels, dtype=bool),
        anomaly_types=np.array(types, dtype=object),
    )
