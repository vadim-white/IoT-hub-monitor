import pytest
from django.test import TestCase, Client
from django.contrib.auth.models import User
from iot_hub.apps.accounts.models import UserRole, UserProfile
from iot_hub.apps.devices.models import Device, DeviceType


@pytest.mark.django_db
class TestUserRegistration(TestCase):
    """Тесты регистрации пользователей."""
    
    def setUp(self):
        self.client = Client()
        self.register_url = '/auth/login/'
    
    def test_user_can_register(self):
        """Тест регистрации пользователя через API."""
        data = {
            'username': 'testuser',
            'email': 'test@example.com',
            'password': 'testpass123',
            'password2': 'testpass123'
        }
        response = self.client.post('/api/auth/users/register/', data)
        assert response.status_code == 201
    
    def test_user_role_created(self):
        """Тест создания роли при регистрации."""
        user = User.objects.create_user('testuser', 'test@example.com', 'testpass')
        assert hasattr(user, 'role')
        assert user.role.role == 'client'
    
    def test_user_profile_created(self):
        """Тест создания профиля при регистрации."""
        user = User.objects.create_user('testuser', 'test@example.com', 'testpass')
        assert hasattr(user, 'profile')


@pytest.mark.django_db
class TestDeviceManagement(TestCase):
    """Тесты управления устройствами."""
    
    def setUp(self):
        self.user = User.objects.create_user('testuser', 'test@example.com', 'testpass')
        self.device_type = DeviceType.objects.create(name='Temperature Sensor')
        self.client = Client()
        self.client.login(username='testuser', password='testpass')
    
    def test_create_device(self):
        """Тест создания устройства."""
        device = Device.objects.create(
            serial_number='DEV001',
            name='Test Device',
            device_type=self.device_type,
            owner=self.user
        )
        assert device.owner == self.user
        assert device.status == 'inactive'
    
    def test_device_is_online(self):
        """Тест проверки статуса онлайн устройства."""
        from django.utils import timezone
        from datetime import timedelta
        
        device = Device.objects.create(
            serial_number='DEV001',
            name='Test Device',
            device_type=self.device_type,
            owner=self.user
        )
        
        # Недавно видели
        device.last_seen_at = timezone.now() - timedelta(minutes=1)
        assert device.is_online == True
        
        # Давно видели
        device.last_seen_at = timezone.now() - timedelta(hours=1)
        assert device.is_online == False
