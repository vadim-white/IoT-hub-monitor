from django.contrib import admin
from .models import DeviceType, Device, DeviceMetric, AlertThreshold


@admin.register(DeviceType)
class DeviceTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'manufacturer', 'created_at')
    search_fields = ('name', 'manufacturer')


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ('name', 'serial_number', 'device_type', 'owner', 'status', 'is_active', 'last_seen_at')
    list_filter = ('status', 'is_active', 'device_type')
    search_fields = ('name', 'serial_number', 'owner__username')


@admin.register(DeviceMetric)
class DeviceMetricAdmin(admin.ModelAdmin):
    list_display = ('device', 'metric_type', 'unit', 'is_active')
    list_filter = ('metric_type', 'is_active')
    search_fields = ('device__name',)


@admin.register(AlertThreshold)
class AlertThresholdAdmin(admin.ModelAdmin):
    list_display = ('metric', 'severity', 'lower_bound', 'upper_bound', 'is_active')
    list_filter = ('severity', 'is_active')
