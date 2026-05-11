import pytest
from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone
from iot_hub.apps.devices.models import Device, DeviceType, DeviceMetric, AlertThreshold
from iot_hub.apps.telemetry.models import Telemetry
from iot_hub.apps.alerts.models import Alert


@pytest.mark.django_db
class TestAlertGeneration(TestCase):
    """Тесты генерации алертов."""
    
    def setUp(self):
        self.user = User.objects.create_user('testuser', 'test@example.com', 'testpass')
        self.device_type = DeviceType.objects.create(name='Temperature Sensor')
        self.device = Device.objects.create(
            serial_number='DEV001',
            name='Test Device',
            device_type=self.device_type,
            owner=self.user
        )
        
        self.metric = DeviceMetric.objects.create(
            device=self.device,
            metric_type='temperature',
            name='Room Temperature',
            unit='°C',
            min_value=15,
            max_value=30
        )
        
        self.threshold = AlertThreshold.objects.create(
            metric=self.metric,
            severity='critical',
            upper_bound=35
        )
    
    def test_alert_created_on_threshold_exceed(self):
        """Тест создания алерта при превышении порога."""
        # Значение выше порога
        value = 40
        
        alert = Alert.objects.create(
            device=self.device,
            metric=self.metric,
            threshold=self.threshold,
            severity='critical',
            message=f'Temperature too high: {value}°C',
            value=value
        )
        
        assert alert.severity == 'critical'
        assert alert.status == 'new'
    
    def test_alert_acknowledgement(self):
        """Тест подтверждения алерта."""
        alert = Alert.objects.create(
            device=self.device,
            metric=self.metric,
            severity='warning',
            message='Test alert',
            value=25
        )
        
        alert.status = 'acknowledged'
        alert.acknowledged_by = self.user
        alert.acknowledged_at = timezone.now()
        alert.save()
        
        assert alert.status == 'acknowledged'
        assert alert.acknowledged_by == self.user


@pytest.mark.django_db
class TestTelemetryHistory(TestCase):
    """Тесты истории телеметрии."""
    
    def setUp(self):
        self.user = User.objects.create_user('testuser', 'test@example.com', 'testpass')
        self.device_type = DeviceType.objects.create(name='Sensor')
        self.device = Device.objects.create(
            serial_number='DEV001',
            device_type=self.device_type,
            owner=self.user
        )
        
        self.metric = DeviceMetric.objects.create(
            device=self.device,
            metric_type='temperature',
            name='Temperature',
            unit='°C'
        )
    
    def test_telemetry_created(self):
        """Тест создания записи телеметрии."""
        telemetry = Telemetry.objects.create(
            device=self.device,
            metric=self.metric,
            value=25.5,
            unit='°C',
            status='ok'
        )
        
        assert telemetry.device == self.device
        assert telemetry.value == 25.5
    
    def test_telemetry_ordering(self):
        """Тест сортировки телеметрии по времени."""
        from datetime import timedelta
        
        base_time = timezone.now()
        
        t1 = Telemetry.objects.create(
            device=self.device,
            metric=self.metric,
            value=20,
            recorded_at=base_time - timedelta(hours=1)
        )
        
        t2 = Telemetry.objects.create(
            device=self.device,
            metric=self.metric,
            value=25,
            recorded_at=base_time
        )
        
        telemetry_list = list(Telemetry.objects.all())
        assert telemetry_list[0] == t2  # Новые первыми
        assert telemetry_list[1] == t1
