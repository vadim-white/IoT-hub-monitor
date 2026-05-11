from rest_framework import viewsets, filters, permissions
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from iot_hub.apps.audit.models import AuditLog
from iot_hub.apps.audit.presentation.serializers import AuditLogSerializer


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet для просмотра журнала аудита."""
    serializer_class = AuditLogSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['action', 'actor']
    ordering_fields = ['timestamp', 'action']
    ordering = ['-timestamp']
    pagination_class = PageNumberPagination
    
    def get_queryset(self):
        user = self.request.user
        # Только админы могут видеть все логи, остальные - только свои
        if hasattr(user, 'role') and user.role.is_admin:
            return AuditLog.objects.select_related('actor').all()
        return AuditLog.objects.filter(actor=user).select_related('actor')
