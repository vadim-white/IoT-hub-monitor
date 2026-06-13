"""Тест команды export_training_data (требует БД).

ГЛАВНЫЙ тест — round-trip: export_training_data → load_series_from_csv даёт тот же
TimeSeries, что load_series из той же БД. Это гарантия, что Colab учит на байт-в-байт
тех же данных (values/labels/anomaly_types/timestamps), что и локальный прод.
"""
import csv
from io import StringIO

import numpy as np
import pytest
from django.test import TestCase
from django.core.management import call_command
from django.contrib.auth.models import User
from django.utils import timezone

from iot_hub.apps.devices.models import Device, DeviceType, DeviceMetric
from iot_hub.apps.telemetry.models import Telemetry
from iot_hub.apps.telemetry.ml.dataset_csv import load_series_from_csv
from iot_hub.apps.telemetry.ml.loader import load_series


@pytest.mark.django_db
class TestExportTrainingData(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("u", "u@e.com", "p")
        dtype = DeviceType.objects.create(name="Temp Sensor")
        self.device = Device.objects.create(
            serial_number="DEV001", name="Test", device_type=dtype, owner=self.user)
        self.metric = DeviceMetric.objects.create(
            device=self.device, metric_type="temperature", name="T", unit="°C")
        # второе устройство — проверить фильтрацию по device
        self.other = Device.objects.create(
            serial_number="DEV002", name="Other", device_type=dtype, owner=self.user)
        self.other_metric = DeviceMetric.objects.create(
            device=self.other, metric_type="temperature", name="T", unit="°C")

        start = timezone.now() - timezone.timedelta(days=1)
        rows = []
        for i in range(50):
            is_anom = (i == 30)
            rows.append(Telemetry(
                device=self.device, metric=self.metric,
                value=60.0 if is_anom else 20.0 + (i % 5) * 0.1, unit="°C",
                recorded_at=start + timezone.timedelta(minutes=10 * i),
                raw_data={"anomaly": {"is_anomaly": is_anom,
                                      **({"type": "spike"} if is_anom else {})}},
            ))
        # точка для другого устройства — не должна попасть при фильтре --device DEV001
        rows.append(Telemetry(
            device=self.other, metric=self.other_metric, value=1.0, unit="°C",
            recorded_at=start, raw_data={}))
        Telemetry.objects.bulk_create(rows)

    def _export(self, path, **extra):
        call_command("export_training_data", "--device", "DEV001",
                     "--metric", "temperature", "--output", str(path),
                     stdout=StringIO(), **extra)

    def test_writes_expected_columns(self, tmp_path=None):
        import tempfile, os
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "train.csv")
            self._export(path)
            with open(path, newline="", encoding="utf-8") as f:
                reader = csv.reader(f)
                header = next(reader)
                first = next(reader)
        assert header == ["device", "metric", "value", "recorded_at",
                          "is_anomaly", "anomaly_type"]
        assert first[0] == "DEV001" and first[1] == "temperature"

    def test_filters_out_other_device(self):
        import tempfile, os
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "train.csv")
            self._export(path)
            with open(path, newline="", encoding="utf-8") as f:
                devices = {row["device"] for row in csv.DictReader(f)}
        assert devices == {"DEV001"}

    def test_anomaly_label_is_written(self):
        import tempfile, os
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "train.csv")
            self._export(path)
            with open(path, newline="", encoding="utf-8") as f:
                anoms = [r for r in csv.DictReader(f) if r["is_anomaly"] == "True"]
        assert len(anoms) == 1
        assert anoms[0]["anomaly_type"] == "spike"

    def test_roundtrip_matches_load_series(self):
        """export → load_series_from_csv == load_series из той же БД."""
        import tempfile, os
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "train.csv")
            self._export(path)
            from_csv = load_series_from_csv(path, "DEV001", "temperature")
        from_db = load_series(self.device, self.metric)

        assert len(from_csv) == len(from_db)
        np.testing.assert_array_equal(from_csv.timestamps, from_db.timestamps)
        np.testing.assert_allclose(from_csv.values, from_db.values)
        np.testing.assert_array_equal(from_csv.labels, from_db.labels)
        np.testing.assert_array_equal(from_csv.anomaly_types, from_db.anomaly_types)

    def test_empty_filter_warns(self):
        import tempfile, os
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "train.csv")
            err = StringIO()
            call_command("export_training_data", "--device", "NOPE",
                         "--output", path, stdout=StringIO(), stderr=err)
            assert "Нет телеметрии" in err.getvalue()
