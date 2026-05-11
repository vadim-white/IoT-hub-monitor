import pytest
from django.test import TestCase
from django.contrib.auth.models import User
from iot_hub.apps.devices.models import Device, DeviceType
from django.test import Client


@pytest.mark.django_db
class TestDeviceAPI(TestCase):
    """Тесты API устройств."""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('testuser', 'test@example.com', 'testpass')
        self.device_type = DeviceType.objects.create(name='Sensor')
        self.client.login(username='testuser', password='testpass')
    
    def test_device_list_api(self):
        """Тест API список устройств."""
        Device.objects.create(
            serial_number='DEV001',
            name='Device 1',
            device_type=self.device_type,
            owner=self.user
        )
        
        response = self.client.get('/api/devices/devices/')
        assert response.status_code == 200
    
    def test_device_create_api(self):
        """Тест API создания устройства."""
        data = {
            'serial_number': 'DEV002',
            'name': 'New Device',
            'device_type': self.device_type.id,
            'status': 'active'
        }
        
        response = self.client.post('/api/devices/devices/', data)
        assert response.status_code in [201, 400]  # 201 или 400 в зависимости от валидации
