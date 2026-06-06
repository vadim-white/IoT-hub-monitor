from django.contrib import admin
from .models import Telemetry, TelemetryBatch, TelemetryStatistics


@admin.register(Telemetry)
class TelemetryAdmin(admin.ModelAdmin):
    list_display = ('device', 'metric', 'value', 'unit', 'recorded_at')
    list_filter = ('metric__metric_type',)
    search_fields = ('device__name',)


@admin.register(TelemetryBatch)
class TelemetryBatchAdmin(admin.ModelAdmin):
    list_display = ('device', 'count', 'processed', 'received_at')
    list_filter = ('processed',)
    search_fields = ('device__name',)


@admin.register(TelemetryStatistics)
class TelemetryStatisticsAdmin(admin.ModelAdmin):
    list_display = ('metric', 'count', 'min_value', 'max_value', 'avg_value', 'last_updated')
    search_fields = ('metric__device__name',)
