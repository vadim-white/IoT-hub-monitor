from rest_framework import serializers
from iot_hub.apps.telemetry.models import Telemetry, TelemetryBatch, TelemetryStatistics
from iot_hub.apps.devices.presentation.serializers import DeviceMetricSerializer


class TelemetrySerializer(serializers.ModelSerializer):
    metric_name = serializers.CharField(source='metric.name', read_only=True)
    device_name = serializers.CharField(source='device.name', read_only=True)
    metric_details = DeviceMetricSerializer(source='metric', read_only=True)
    
    class Meta:
        model = Telemetry
        fields = ['id', 'device', 'device_name', 'metric', 'metric_name', 'metric_details',
                  'value', 'unit', 'status', 'raw_data', 'recorded_at']
        read_only_fields = ['id', 'recorded_at']


class TelemetryCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Telemetry
        fields = ['device', 'metric', 'value', 'unit', 'status', 'raw_data']


class TelemetryBatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = TelemetryBatch
        fields = ['id', 'device', 'data', 'count', 'processed', 'received_at', 'processed_at']
        read_only_fields = ['id', 'processed_at']


class TelemetryStatisticsSerializer(serializers.ModelSerializer):
    metric_details = DeviceMetricSerializer(source='metric', read_only=True)
    
    class Meta:
        model = TelemetryStatistics
        fields = ['id', 'metric', 'metric_details', 'count', 'min_value', 'max_value', 
                  'avg_value', 'last_updated']
        read_only_fields = ['id', 'count', 'min_value', 'max_value', 'avg_value', 'last_updated']
