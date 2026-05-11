from django.db import models


class DashboardSettings(models.Model):
    """Настройки дашборда пользователя."""
    user = models.OneToOneField('auth.User', on_delete=models.CASCADE, related_name='dashboard_settings')
    
    widgets = models.JSONField(default=list, blank=True)
    theme = models.CharField(
        max_length=20,
        choices=[('light', 'Светлая'), ('dark', 'Темная')],
        default='light'
    )
    auto_refresh_interval = models.IntegerField(default=30)  # в секундах
    
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Настройки дашборда'
        verbose_name_plural = 'Настройки дашбордов'
        db_table = 'dashboard_settings'
    
    def __str__(self):
        return f"Dashboard settings for {self.user.username}"
