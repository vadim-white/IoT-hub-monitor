"""Тест management-команды detect_anomalies (требует БД)."""
from io import StringIO

import pytest
from django.test import TestCase
from django.core.management import call_command
from django.contrib.auth.models import User
from django.utils import timezone

from iot_hub.apps.devices.models import Device, DeviceType, DeviceMetric
from iot_hub.apps.telemetry.models import Telemetry


@pytest.mark.django_db
class TestDetectAnomaliesCommand(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("u", "u@e.com", "p")
        dtype = DeviceType.objects.create(name="Temp Sensor")
        self.device = Device.objects.create(
            serial_number="DEV001", name="Test", device_type=dtype, owner=self.user)
        self.metric = DeviceMetric.objects.create(
            device=self.device, metric_type="temperature", name="T", unit="°C")

        # 300 точек: норма ~20°C + один спайк с меткой ground-truth
        start = timezone.now() - timezone.timedelta(days=3)
        rows = []
        for i in range(300):
            is_anom = (i == 200)
            value = 60.0 if is_anom else 20.0 + (i % 5) * 0.1
            rows.append(Telemetry(
                device=self.device, metric=self.metric, value=value, unit="°C",
                recorded_at=start + timezone.timedelta(minutes=10 * i),
                raw_data={"synthetic": True,
                          "anomaly": {"is_anomaly": is_anom,
                                      **({"type": "spike", "severity": "high"} if is_anom else {})}},
            ))
        Telemetry.objects.bulk_create(rows)

    def test_runs_and_reports_metrics(self):
        out = StringIO()
        call_command("detect_anomalies", "--device", "DEV001",
                     "--metric", "temperature", "--method", "zscore",
                     "--window", "24", "--threshold", "3.0", stdout=out)
        text = out.getvalue()
        assert "precision" in text
        assert "recall" in text
        assert "DEV001" in text

    def test_detects_the_injected_spike(self):
        """Спайк в индексе 200 должен дать recall > 0 (TP >= 1)."""
        out = StringIO()
        call_command("detect_anomalies", "--device", "DEV001",
                     "--metric", "temperature", stdout=out)
        text = out.getvalue()
        assert "ИТОГО" in text
        # recall не нулевой — спайк пойман
        assert "recall=0.000" not in text.split("ИТОГО")[1]

    def test_json_report(self):
        out = StringIO()
        call_command("detect_anomalies", "--device", "DEV001",
                     "--report", "json", stdout=out)
        import json
        payload = json.loads(out.getvalue())
        assert payload[0]["device"] == "DEV001"
        assert payload[0]["method"] == "zscore"
        assert "precision" in payload[0]

    def test_does_not_create_alerts(self):
        """Baseline-команда только оценивает — Alert не создаёт."""
        from iot_hub.apps.alerts.models import Alert
        before = Alert.objects.count()
        call_command("detect_anomalies", "--device", "DEV001", stdout=StringIO())
        assert Alert.objects.count() == before

    def test_iforest_method_runs(self):
        """Метод iforest отрабатывает, IF-параметры пробрасываются."""
        pytest.importorskip("sklearn")
        out = StringIO()
        call_command("detect_anomalies", "--device", "DEV001", "--metric", "temperature",
                     "--method", "iforest", "--window", "24", "--threshold", "0.0",
                     "--contamination", "0.05", stdout=out)
        text = out.getvalue()
        assert "method=iforest" in text
        assert "precision" in text

    def test_autoencoder_method_runs(self):
        """Метод autoencoder отрабатывает, AE-параметры пробрасываются."""
        pytest.importorskip("torch")
        out = StringIO()
        call_command("detect_anomalies", "--device", "DEV001", "--metric", "temperature",
                     "--method", "autoencoder", "--window", "24", "--epochs", "5",
                     "--latent-dim", "4", stdout=out)
        text = out.getvalue()
        assert "method=autoencoder" in text
        assert "precision" in text

    def test_train_models_then_use_cache_loads(self, tmp_path=None):
        """train_models сохраняет артефакт; detect_anomalies --use-cache его грузит,
        а не переобучает (логирует [cache] загружено)."""
        pytest.importorskip("sklearn")
        import tempfile
        from pathlib import Path
        from unittest import mock
        from iot_hub.apps.telemetry.ml import persistence

        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(persistence, "ML_MODELS_DIR", Path(d)):
                # обучаем и сохраняем
                train_out = StringIO()
                call_command("train_models", "--device", "DEV001",
                             "--metric", "temperature", "--method", "iforest",
                             "--window", "24", stdout=train_out)
                assert "Обучено и сохранено моделей: 1" in train_out.getvalue()
                # схема инкр.7: <models>/<device>/<name>__<metric>.manifest.json
                assert (Path(d) / "DEV001" / "iforest__temperature.manifest.json").exists()

                # повторный детект с --use-cache грузит веса
                det_out = StringIO()
                call_command("detect_anomalies", "--device", "DEV001",
                             "--metric", "temperature", "--method", "iforest",
                             "--window", "24", "--use-cache", stdout=det_out)
                assert "[cache] загружено" in det_out.getvalue()

    def test_use_cache_miss_falls_back_to_fit(self):
        """Без сохранённого артефакта --use-cache не падает, а обучает (miss)."""
        pytest.importorskip("sklearn")
        import tempfile
        from pathlib import Path
        from unittest import mock
        from iot_hub.apps.telemetry.ml import persistence

        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(persistence, "ML_MODELS_DIR", Path(d)):
                out = StringIO()
                call_command("detect_anomalies", "--device", "DEV001",
                             "--metric", "temperature", "--method", "iforest",
                             "--window", "24", "--use-cache", stdout=out)
                assert "[cache] miss" in out.getvalue()
                assert "precision" in out.getvalue()
