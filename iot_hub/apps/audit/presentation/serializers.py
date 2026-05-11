from rest_framework import serializers
from iot_hub.apps.audit.models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source='actor.username', read_only=True)
    
    class Meta:
        model = AuditLog
        fields = ['id', 'actor', 'actor_name', 'action', 'object_repr', 
                  'changes', 'ip_address', 'timestamp', 'changed_fields']
        read_only_fields = ['id', 'timestamp', 'changed_fields']
