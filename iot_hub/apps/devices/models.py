from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import uuid


class DeviceType(models.Model):
    """Типы IoT-устройств."""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    manufacturer = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'Тип устройства'
        verbose_name_plural = 'Типы устройств'
        db_table = 'devices_devicetype'
    
    def __str__(self):
        return self.name


class Device(models.Model):
    """IoT-устройства для мониторинга."""
    STATUS_CHOICES = (
        ('active', 'Активно'),
        ('inactive', 'Неактивно'),
        ('disconnected', 'Отключено'),
        ('error', 'Ошибка'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    serial_number = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    device_type = models.ForeignKey(DeviceType, on_delete=models.SET_NULL, null=True)
    owner = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='owned_devices')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='inactive')
    
    latitude = models.FloatField(blank=True, null=True)
    longitude = models.FloatField(blank=True, null=True)
    location_name = models.CharField(max_length=255, blank=True)
    
    is_active = models.BooleanField(default=True)
    installation_date = models.DateTimeField(blank=True, null=True)
    last_seen_at = models.DateTimeField(blank=True, null=True)
    
    metadata = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'IoT-устройство'
        verbose_name_plural = 'IoT-устройства'
        db_table = 'devices_device'
        indexes = [
            models.Index(fields=['owner', 'status']),
            models.Index(fields=['last_seen_at']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.serial_number})"
    
    @property
    def is_online(self):
        from django.utils import timezone
        from datetime import timedelta
        if not self.last_seen_at:
            return False
        return (timezone.now() - self.last_seen_at) < timedelta(minutes=5)


class DeviceMetric(models.Model):
    """Допустимые метрики для устройств."""
    METRIC_TYPES = (
        ('temperature', 'Температура (°C)'),
        ('humidity', 'Влажность (%)'),
        ('voltage', 'Напряжение (V)'),
        ('current', 'Ток (A)'),
        ('power', 'Мощность (W)'),
        ('rssi', 'Сила сигнала (dBm)'),
        ('uptime', 'Время работы (s)'),
        ('error_count', 'Количество ошибок'),
        ('custom', 'Пользовательский'),
    )
    
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='metrics')
    metric_type = models.CharField(max_length=50, choices=METRIC_TYPES)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    unit = models.CharField(max_length=50, blank=True)
    min_value = models.FloatField(blank=True, null=True)
    max_value = models.FloatField(blank=True, null=True)
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Метрика устройства'
        verbose_name_plural = 'Метрики устройств'
        db_table = 'devices_devicemetric'
        unique_together = ('device', 'metric_type')
    
    def __str__(self):
        return f"{self.device.name} - {self.get_metric_type_display()}"


class AlertThreshold(models.Model):
    """Пороги для генерации алертов."""
    SEVERITY_LEVELS = (
        ('info', 'Информация'),
        ('warning', 'Предупреждение'),
        ('critical', 'Критичный'),
    )
    
    metric = models.ForeignKey(DeviceMetric, on_delete=models.CASCADE, related_name='thresholds')
    severity = models.CharField(max_length=20, choices=SEVERITY_LEVELS, default='warning')
    lower_bound = models.FloatField(blank=True, null=True)
    upper_bound = models.FloatField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Порог алерта'
        verbose_name_plural = 'Пороги алертов'
        db_table = 'devices_alertthreshold'
    
    def __str__(self):
        return f"{self.metric.name} - {self.get_severity_display()}"
    
    def check_threshold(self, value):
        """Проверяет, превышен ли порог."""
        if self.lower_bound is not None and value < self.lower_bound:
            return True
        if self.upper_bound is not None and value > self.upper_bound:
            return True
        return False
