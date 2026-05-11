from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from rest_framework import viewsets, status, filters, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from iot_hub.apps.alerts.models import Alert, AlertNotification, AlertHistory
from iot_hub.apps.alerts.presentation.serializers import (
    AlertSerializer, AlertNotificationSerializer, AlertHistorySerializer,
    AlertCreateSerializer, AlertUpdateSerializer
)
from iot_hub.apps.devices.models import Device


# ====== WEB VIEWS ======

@login_required(login_url='login')
def alerts_list(request):
    """Список всех алертов для пользователя."""
    if hasattr(request.user, 'role') and request.user.role.is_admin:
        alerts = Alert.objects.select_related('device', 'metric').all()
    else:
        alerts = Alert.objects.filter(device__owner=request.user).select_related('device', 'metric')
    
    # Фильтрация по статусу
    status_filter = request.GET.get('status')
    if status_filter:
        alerts = alerts.filter(status=status_filter)
    
    severity_filter = request.GET.get('severity')
    if severity_filter:
        alerts = alerts.filter(severity=severity_filter)
    
    context = {
        'alerts': alerts[:100],
        'new_count': alerts.filter(status='new').count(),
        'acknowledged_count': alerts.filter(status='acknowledged').count(),
        'resolved_count': alerts.filter(status='resolved').count(),
        'critical_count': alerts.filter(severity='critical').count(),
    }
    return render(request, 'alerts/list.html', context)


# ====== API VIEWS ======

class AlertViewSet(viewsets.ModelViewSet):
    """ViewSet для управления алертами."""
    serializer_class = AlertSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['device', 'status', 'severity']
    ordering_fields = ['created_at', 'severity']
    ordering = ['-created_at']
    pagination_class = PageNumberPagination
    
    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'role') and user.role.is_admin:
            return Alert.objects.select_related('device', 'metric').prefetch_related('history', 'notifications')
        return Alert.objects.filter(device__owner=user).select_related('device', 'metric').prefetch_related('history', 'notifications')
    
    def get_serializer_class(self):
        if self.action == 'create':
            return AlertCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return AlertUpdateSerializer
        return AlertSerializer
    
    @action(detail=True, methods=['post'])
    def acknowledge(self, request, pk=None):
        """Подтвердить алерт."""
        alert = self.get_object()
        alert.status = 'acknowledged'
        alert.acknowledged_by = request.user
        alert.acknowledged_at = timezone.now()
        alert.save()
        
        # Создаем запись в истории
        AlertHistory.objects.create(
            alert=alert,
            action='acknowledged',
            actor=request.user
        )
        
        return Response({'status': 'Alert acknowledged'})
    
    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        """Разрешить алерт."""
        alert = self.get_object()
        alert.status = 'resolved'
        alert.resolved_by = request.user
        alert.resolved_at = timezone.now()
        alert.save()
        
        AlertHistory.objects.create(
            alert=alert,
            action='resolved',
            actor=request.user,
            comment=request.data.get('comment', '')
        )
        
        return Response({'status': 'Alert resolved'})
    
    @action(detail=True, methods=['post'])
    def close(self, request, pk=None):
        """Закрыть алерт."""
        alert = self.get_object()
        alert.status = 'closed'
        alert.save()
        
        AlertHistory.objects.create(
            alert=alert,
            action='closed',
            actor=request.user
        )
        
        return Response({'status': 'Alert closed'})
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Получить статистику по алертам."""
        queryset = self.get_queryset()
        
        return Response({
            'total': queryset.count(),
            'new': queryset.filter(status='new').count(),
            'acknowledged': queryset.filter(status='acknowledged').count(),
            'resolved': queryset.filter(status='resolved').count(),
            'closed': queryset.filter(status='closed').count(),
            'critical': queryset.filter(severity='critical').count(),
            'warning': queryset.filter(severity='warning').count(),
            'info': queryset.filter(severity='info').count(),
        })


class AlertNotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet для уведомлений об алертах."""
    serializer_class = AlertNotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return AlertNotification.objects.filter(user=self.request.user).select_related('alert')
    
    @action(detail=True, methods=['post'])
    def mark_as_read(self, request, pk=None):
        """Отметить уведомление как прочитанное."""
        notification = self.get_object()
        notification.read_at = timezone.now()
        notification.save()
        return Response({'status': 'Notification marked as read'})


# Import timezone
from django.utils import timezone
