from rest_framework import serializers
from iot_hub.apps.devices.models import Device, DeviceType, DeviceMetric, AlertThreshold


class DeviceTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceType
        fields = ['id', 'name', 'description', 'manufacturer']


class AlertThresholdSerializer(serializers.ModelSerializer):
    class Meta:
        model = AlertThreshold
        fields = ['id', 'metric', 'severity', 'lower_bound', 'upper_bound', 'is_active']


class DeviceMetricSerializer(serializers.ModelSerializer):
    thresholds = AlertThresholdSerializer(many=True, read_only=True)
    
    class Meta:
        model = DeviceMetric
        fields = ['id', 'device', 'metric_type', 'name', 'description', 'unit', 
                  'min_value', 'max_value', 'is_active', 'thresholds']


class DeviceSerializer(serializers.ModelSerializer):
    metrics = DeviceMetricSerializer(many=True, read_only=True)
    device_type_name = serializers.CharField(source='device_type.name', read_only=True)
    owner_name = serializers.CharField(source='owner.username', read_only=True)
    is_online = serializers.SerializerMethodField()
    
    class Meta:
        model = Device
        fields = ['id', 'serial_number', 'name', 'description', 'device_type', 
                  'device_type_name', 'owner', 'owner_name', 'status', 'is_active',
                  'latitude', 'longitude', 'location_name', 'installation_date',
                  'last_seen_at', 'metadata', 'created_at', 'updated_at', 'is_online',
                  'metrics']
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_is_online(self, obj):
        return obj.is_online


class DeviceCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Device
        fields = ['serial_number', 'name', 'description', 'device_type', 'status',
                  'latitude', 'longitude', 'location_name', 'installation_date', 
                  'is_active', 'metadata']
