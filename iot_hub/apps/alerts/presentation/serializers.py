from rest_framework import serializers
from iot_hub.apps.alerts.models import Alert, AlertNotification, AlertHistory
from iot_hub.apps.devices.presentation.serializers import DeviceMetricSerializer


class AlertHistorySerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source='actor.username', read_only=True)
    
    class Meta:
        model = AlertHistory
        fields = ['id', 'action', 'actor', 'actor_name', 'comment', 'created_at']
        read_only_fields = ['id', 'created_at']


class AlertNotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = AlertNotification
        fields = ['id', 'alert', 'user', 'notification_type', 'sent_at', 
                  'read_at', 'content']
        read_only_fields = ['id', 'sent_at']


class AlertSerializer(serializers.ModelSerializer):
    device_name = serializers.CharField(source='device.name', read_only=True)
    metric_name = serializers.CharField(source='metric.name', read_only=True)
    metric_details = DeviceMetricSerializer(source='metric', read_only=True)
    history = AlertHistorySerializer(many=True, read_only=True)
    notifications = AlertNotificationSerializer(many=True, read_only=True)
    acknowledged_by_name = serializers.CharField(source='acknowledged_by.username', read_only=True)
    resolved_by_name = serializers.CharField(source='resolved_by.username', read_only=True)
    
    class Meta:
        model = Alert
        fields = ['id', 'device', 'device_name', 'metric', 'metric_name', 'metric_details',
                  'threshold', 'severity', 'status', 'message', 'value',
                  'acknowledged_by', 'acknowledged_by_name', 'acknowledged_at',
                  'resolved_by', 'resolved_by_name', 'resolved_at',
                  'telemetry', 'created_at', 'updated_at', 'history', 'notifications']
        read_only_fields = ['id', 'created_at', 'updated_at']


class AlertCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Alert
        fields = ['device', 'metric', 'severity', 'message', 'value']


class AlertUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Alert
        fields = ['status', 'acknowledged_by', 'resolved_by']
