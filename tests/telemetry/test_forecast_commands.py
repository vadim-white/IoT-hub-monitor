"""Smoke-тесты команд forecast_telemetry и predict_threshold (требуют БД)."""
from io import StringIO

import numpy as np
import pytest
from django.test import TestCase
from django.core.management import call_command
from django.contrib.auth.models import User
from django.utils import timezone

from iot_hub.apps.devices.models import Device, DeviceType, DeviceMetric
from iot_hub.apps.telemetry.models import Telemetry


@pytest.mark.django_db
class TestForecastCommands(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("u", "u@e.com", "p")
        dtype = DeviceType.objects.create(name="Temp Sensor")
        self.device = Device.objects.create(
            serial_number="DEV001", name="Test", device_type=dtype, owner=self.user)
        self.metric = DeviceMetric.objects.create(
            device=self.device, metric_type="temperature", name="T", unit="°C")

        # 500 точек сезонного ряда (период 24) — достаточно для naive backtest
        start = timezone.now() - timezone.timedelta(days=4)
        rows = []
        for i in range(500):
            value = 20.0 + 5 * np.sin(2 * np.pi * i / 24)
            rows.append(Telemetry(
                device=self.device, metric=self.metric, value=float(value), unit="°C",
                recorded_at=start + timezone.timedelta(minutes=10 * i),
                raw_data={"synthetic": True, "anomaly": {"is_anomaly": False}},
            ))
        Telemetry.objects.bulk_create(rows)

    def test_forecast_telemetry_runs(self):
        out = StringIO()
        call_command("forecast_telemetry", "--device", "DEV001", "--metric", "temperature",
                     "--method", "naive", "--horizon", "24", "--seasonal-periods", "24",
                     "--initial-train", "200", "--step", "50", stdout=out)
        text = out.getvalue()
        assert "MAE" in text
        assert "naive" in text

    def test_predict_threshold_with_cli_bound(self):
        out = StringIO()
        call_command("predict_threshold", "--device", "DEV001", "--metric", "temperature",
                     "--method", "naive", "--seasonal-periods", "24", "--horizon", "24",
                     "--upper-bound", "10", stdout=out)  # порог 10 ниже ряда → пересечёт
        text = out.getvalue()
        assert "DEV001" in text
        assert "upper_bound" in text or "пересеч" in text
