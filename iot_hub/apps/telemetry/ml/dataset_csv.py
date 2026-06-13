"""Сборка TimeSeries из CSV — офлайн-зеркало loader.load_series (Фаза 4, инкр. 2).

loader.py тянет Django ORM и в Colab недоступен. Этот модуль собирает тот же
TimeSeries из плоского CSV, выгруженного командой export_training_data, — чтобы
обучение в Colab шло на байт-в-байт тех же данных, что и локальный прод.

Django-независим (как dataset.py): чистый csv/numpy. CSV-формат параллелен
loader.load_series (loader.py:32-37): те же поля, та же трактовка меток
(нет метки → нормальная точка). Round-trip-тест гарантирует равенство TimeSeries
из CSV и из БД.

Колонки CSV: device,metric,value,recorded_at,is_anomaly,anomaly_type.
"""
from __future__ import annotations

import csv

import numpy as np

from .dataset import TimeSeries

# truthy-значения is_anomaly: csv хранит всё строками, поддержим оба варианта
_TRUE = {"true", "1", "yes"}


def load_series_from_csv(path, device: str, metric: str) -> TimeSeries:
    """Собирает TimeSeries по (device, metric) из CSV, строго по возрастанию времени.

    device/metric — строки (serial_number / metric_type), как в колонках CSV.
    Строки фильтруются по совпадению обеих колонок; порядок берётся как в файле
    (export_training_data сортирует по (device, metric, recorded_at)).
    """
    values: list[float] = []
    timestamps: list = []
    labels: list[bool] = []
    types: list[str] = []

    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["device"] != device or row["metric"] != metric:
                continue
            values.append(float(row["value"]))
            # recorded_at пишется в ISO без tz (как load_series делает .replace(tzinfo=None))
            timestamps.append(np.datetime64(row["recorded_at"]))
            is_anomaly = row.get("is_anomaly", "").strip().lower() in _TRUE
            labels.append(is_anomaly)
            types.append(row.get("anomaly_type", "") if is_anomaly else "")

    return TimeSeries(
        timestamps=np.array(timestamps, dtype="datetime64[ns]"),
        values=np.array(values, dtype=float),
        labels=np.array(labels, dtype=bool),
        anomaly_types=np.array(types, dtype=object),
    )
