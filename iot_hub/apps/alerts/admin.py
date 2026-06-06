from django.contrib import admin
from .models import Alert, AlertNotification, AlertHistory


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ('device', 'severity', 'status', 'message', 'created_at')
    list_filter = ('severity', 'status')
    search_fields = ('device__name', 'message')


@admin.register(AlertNotification)
class AlertNotificationAdmin(admin.ModelAdmin):
    list_display = ('alert', 'user', 'notification_type', 'sent_at')
    list_filter = ('notification_type',)
    search_fields = ('alert__device__name', 'user__username')


@admin.register(AlertHistory)
class AlertHistoryAdmin(admin.ModelAdmin):
    list_display = ('alert', 'action', 'actor', 'created_at')
    list_filter = ('action',)
    search_fields = ('alert__device__name', 'actor__username')
