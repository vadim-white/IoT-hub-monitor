"""Юнит-тесты load_series_from_csv. Чистое ядро — без БД, без @django_db.

Round-trip vs load_series (из БД) живёт в test_export_training_data.py — здесь
проверяем парсер изолированно: колонки, метки, фильтрация, пустой/без-меток CSV.
"""
import csv

import numpy as np

from iot_hub.apps.telemetry.ml.dataset_csv import load_series_from_csv

COLUMNS = ["device", "metric", "value", "recorded_at", "is_anomaly", "anomaly_type"]


def _write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)


def test_parses_values_and_labels(tmp_path):
    p = tmp_path / "t.csv"
    _write_csv(p, [
        {"device": "D1", "metric": "temperature", "value": "20.5",
         "recorded_at": "2025-01-01T00:00:00", "is_anomaly": "False", "anomaly_type": ""},
        {"device": "D1", "metric": "temperature", "value": "99.0",
         "recorded_at": "2025-01-01T00:10:00", "is_anomaly": "True", "anomaly_type": "spike"},
    ])
    s = load_series_from_csv(p, "D1", "temperature")

    assert len(s) == 2
    np.testing.assert_allclose(s.values, [20.5, 99.0])
    assert s.labels.tolist() == [False, True]
    assert s.anomaly_types.tolist() == ["", "spike"]
    assert s.timestamps.dtype == np.dtype("datetime64[ns]")


def test_filters_by_device_and_metric(tmp_path):
    p = tmp_path / "t.csv"
    _write_csv(p, [
        {"device": "D1", "metric": "temperature", "value": "1",
         "recorded_at": "2025-01-01T00:00:00", "is_anomaly": "False", "anomaly_type": ""},
        {"device": "D2", "metric": "temperature", "value": "2",
         "recorded_at": "2025-01-01T00:00:00", "is_anomaly": "False", "anomaly_type": ""},
        {"device": "D1", "metric": "humidity", "value": "3",
         "recorded_at": "2025-01-01T00:00:00", "is_anomaly": "False", "anomaly_type": ""},
    ])
    s = load_series_from_csv(p, "D1", "temperature")
    np.testing.assert_allclose(s.values, [1.0])


def test_anomaly_type_dropped_when_not_anomaly(tmp_path):
    # параллель loader.py: тип засчитывается только при is_anomaly=True
    p = tmp_path / "t.csv"
    _write_csv(p, [
        {"device": "D1", "metric": "temperature", "value": "1",
         "recorded_at": "2025-01-01T00:00:00", "is_anomaly": "False", "anomaly_type": "spike"},
    ])
    s = load_series_from_csv(p, "D1", "temperature")
    assert s.anomaly_types.tolist() == [""]


def test_empty_match_does_not_crash(tmp_path):
    p = tmp_path / "t.csv"
    _write_csv(p, [
        {"device": "D2", "metric": "temperature", "value": "1",
         "recorded_at": "2025-01-01T00:00:00", "is_anomaly": "False", "anomaly_type": ""},
    ])
    s = load_series_from_csv(p, "D1", "temperature")
    assert len(s) == 0
