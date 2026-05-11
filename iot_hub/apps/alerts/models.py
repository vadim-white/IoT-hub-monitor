from django.db import models
from django.contrib.auth.models import User
from iot_hub.apps.devices.models import Device, DeviceMetric, AlertThreshold
from iot_hub.apps.telemetry.models import Telemetry


class Alert(models.Model):
    """Алерты, генерируемые при превышении порогов."""
    STATUS_CHOICES = (
        ('new', 'Новый'),
        ('acknowledged', 'Подтвержден'),
        ('resolved', 'Разрешен'),
        ('closed', 'Закрыт'),
    )
    
    SEVERITY_CHOICES = (
        ('info', 'Информация'),
        ('warning', 'Предупреждение'),
        ('critical', 'Критичный'),
    )
    
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='alerts')
    metric = models.ForeignKey(DeviceMetric, on_delete=models.CASCADE, related_name='alerts')
    threshold = models.ForeignKey(AlertThreshold, on_delete=models.SET_NULL, null=True, related_name='alerts')
    telemetry = models.ForeignKey(Telemetry, on_delete=models.SET_NULL, null=True, related_name='alert')
    
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='warning')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')
    
    message = models.TextField()
    value = models.FloatField()
    
    acknowledged_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='acknowledged_alerts'
    )
    acknowledged_at = models.DateTimeField(blank=True, null=True)
    
    resolved_at = models.DateTimeField(blank=True, null=True)
    resolved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='resolved_alerts'
    )
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Алерт'
        verbose_name_plural = 'Алерты'
        db_table = 'alerts_alert'
        indexes = [
            models.Index(fields=['device', 'status']),
            models.Index(fields=['severity', '-created_at']),
            models.Index(fields=['-created_at']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Alert [{self.get_severity_display()}] - {self.device.name}: {self.message}"


class AlertNotification(models.Model):
    """Уведомления об алертах."""
    NOTIFICATION_TYPES = (
        ('email', 'Email'),
        ('sms', 'SMS'),
        ('push', 'Push'),
        ('in_app', 'In-App'),
    )
    
    alert = models.ForeignKey(Alert, on_delete=models.CASCADE, related_name='notifications')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='alert_notifications')
    
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    sent_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(blank=True, null=True)
    
    content = models.TextField()
    external_id = models.CharField(max_length=255, blank=True)
    
    class Meta:
        verbose_name = 'Уведомление об алерте'
        verbose_name_plural = 'Уведомления об алертах'
        db_table = 'alerts_notification'
        ordering = ['-sent_at']
    
    def __str__(self):
        return f"Notification for alert {self.alert.id} to {self.user.username}"


class AlertHistory(models.Model):
    """История изменения алертов."""
    ACTION_CHOICES = (
        ('created', 'Создан'),
        ('acknowledged', 'Подтвержден'),
        ('resolved', 'Разрешен'),
        ('closed', 'Закрыт'),
        ('reopened', 'Переоткрыт'),
    )
    
    alert = models.ForeignKey(Alert, on_delete=models.CASCADE, related_name='history')
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    comment = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'История алерта'
        verbose_name_plural = 'Истории алертов'
        db_table = 'alerts_history'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Alert {self.alert.id} - {self.get_action_display()}"
