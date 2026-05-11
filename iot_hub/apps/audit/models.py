from django.db import models
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType


class AuditLog(models.Model):
    """Журнал аудита всех действий в системе."""
    ACTION_TYPES = (
        ('create', 'Создание'),
        ('update', 'Обновление'),
        ('delete', 'Удаление'),
        ('login', 'Вход'),
        ('logout', 'Выход'),
        ('threshold_change', 'Изменение порога'),
        ('alert_action', 'Действие с алертом'),
        ('device_action', 'Действие с устройством'),
        ('export', 'Экспорт'),
        ('import', 'Импорт'),
        ('config_change', 'Изменение конфигурации'),
    )
    
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='audit_logs')
    action = models.CharField(max_length=50, choices=ACTION_TYPES)
    
    content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    object_repr = models.CharField(max_length=255, blank=True)
    
    changes = models.JSONField(default=dict, blank=True)
    
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.TextField(blank=True)
    
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        verbose_name = 'Запись аудита'
        verbose_name_plural = 'Записи аудита'
        db_table = 'audit_auditlog'
        indexes = [
            models.Index(fields=['actor', '-timestamp']),
            models.Index(fields=['action', '-timestamp']),
            models.Index(fields=['content_type', 'object_id']),
        ]
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"{self.get_action_display()} by {self.actor} at {self.timestamp}"
    
    @property
    def changed_fields(self):
        """Возвращает список измененных полей."""
        if isinstance(self.changes, dict):
            return list(self.changes.keys())
        return []
