"""Тесты helper'а create_ml_alert: создание ML-алерта, metadata, дедупликация."""
import pytest
from django.contrib.auth.models import User
from django.test import TestCase

from iot_hub.apps.alerts.application.ml_alerts import create_ml_alert
from iot_hub.apps.alerts.models import Alert, AlertHistory
from iot_hub.apps.devices.models import Device, DeviceMetric, DeviceType


@pytest.mark.django_db
class TestCreateMLAlert(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('u', 'u@e.com', 'p')
        dt = DeviceType.objects.create(name='Temp')
        self.device = Device.objects.create(
            serial_number='D1', name='Dev', device_type=dt, owner=self.user)
        self.metric = DeviceMetric.objects.create(
            device=self.device, metric_type='temperature', name='T', unit='°C')

    def _create(self, source='ml_anomaly', **kw):
        return create_ml_alert(
            device=self.device, metric=self.metric, source=source,
            severity='warning', value=42.0, message='тест',
            metadata={'method': 'iforest', 'score': 0.9}, **kw)

    def test_creates_alert_with_source_and_metadata(self):
        alert, created = self._create()
        assert created is True
        assert alert.source == 'ml_anomaly'
        assert alert.status == 'new'
        assert alert.threshold is None
        assert alert.metadata['method'] == 'iforest'

    def test_writes_history_record(self):
        alert, _ = self._create()
        assert AlertHistory.objects.filter(alert=alert, action='created').exists()

    def test_dedup_returns_existing_within_window(self):
        first, c1 = self._create()
        second, c2 = self._create()
        assert c1 is True and c2 is False
        assert first.pk == second.pk
        assert Alert.objects.filter(source='ml_anomaly').count() == 1

    def test_dedup_disabled_creates_duplicate(self):
        self._create(dedup_hours=0)
        self._create(dedup_hours=0)
        assert Alert.objects.filter(source='ml_anomaly').count() == 2

    def test_dedup_is_per_source(self):
        self._create(source='ml_anomaly')
        _, created = self._create(source='ml_forecast')
        assert created is True
        assert Alert.objects.count() == 2

    def test_resolved_alert_does_not_block_new(self):
        first, _ = self._create()
        first.status = 'resolved'
        first.save()
        _, created = self._create()
        assert created is True
        assert Alert.objects.filter(source='ml_anomaly').count() == 2
