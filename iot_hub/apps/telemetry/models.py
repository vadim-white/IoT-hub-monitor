from django.db import models
from iot_hub.apps.devices.models import Device, DeviceMetric


class Telemetry(models.Model):
    """Временной ряд телеметрических данных от устройств."""
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='telemetry')
    metric = models.ForeignKey(DeviceMetric, on_delete=models.CASCADE, related_name='readings')
    
    value = models.FloatField()
    unit = models.CharField(max_length=50, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[('ok', 'OK'), ('warning', 'Warning'), ('error', 'Error')],
        default='ok'
    )
    
    raw_data = models.JSONField(default=dict, blank=True)
    
    recorded_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        verbose_name = 'Телеметрия'
        verbose_name_plural = 'Телеметрии'
        db_table = 'telemetry_telemetry'
        indexes = [
            models.Index(fields=['device', '-recorded_at']),
            models.Index(fields=['metric', '-recorded_at']),
            models.Index(fields=['recorded_at']),
        ]
        ordering = ['-recorded_at']
    
    def __str__(self):
        return f"{self.device.name} - {self.metric.name}: {self.value}{self.unit}"


class TelemetryBatch(models.Model):
    """Пакеты приема телеметрии для оптимизации."""
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='telemetry_batches')
    
    data = models.JSONField()
    count = models.IntegerField()
    processed = models.BooleanField(default=False)
    
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        verbose_name = 'Пакет телеметрии'
        verbose_name_plural = 'Пакеты телеметрии'
        db_table = 'telemetry_telemetrybatch'
        ordering = ['-received_at']
    
    def __str__(self):
        return f"Batch {self.id} - {self.device.name} ({self.count} readings)"


class TelemetryStatistics(models.Model):
    """Кэшированная статистика по метрикам."""
    metric = models.OneToOneField(DeviceMetric, on_delete=models.CASCADE, related_name='statistics')
    
    count = models.IntegerField(default=0)
    min_value = models.FloatField(blank=True, null=True)
    max_value = models.FloatField(blank=True, null=True)
    avg_value = models.FloatField(blank=True, null=True)
    
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Статистика телеметрии'
        verbose_name_plural = 'Статистика телеметрии'
        db_table = 'telemetry_statistics'
    
    def __str__(self):
        return f"Stats for {self.metric.name}"
