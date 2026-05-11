from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from iot_hub.apps.dashboard.models import DashboardSettings
from iot_hub.apps.devices.models import Device
from iot_hub.apps.alerts.models import Alert
from iot_hub.apps.telemetry.models import Telemetry
from django.utils import timezone
from datetime import timedelta


class DashboardViewSet(viewsets.ViewSet):
    """API для дашборда."""
    permission_classes = [permissions.IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Получить статистику для дашборда."""
        user = request.user
        
        if hasattr(user, 'role') and user.role.is_admin:
            devices = Device.objects.all()
            alerts = Alert.objects.all()
        else:
            devices = Device.objects.filter(owner=user)
            alerts = Alert.objects.filter(device__owner=user)
        
        last_24h = timezone.now() - timedelta(hours=24)
        
        return Response({
            'devices': {
                'total': devices.count(),
                'active': devices.filter(status='active').count(),
                'inactive': devices.filter(status='inactive').count(),
                'online': sum(1 for d in devices if d.is_online),
            },
            'alerts': {
                'total': alerts.count(),
                'new': alerts.filter(status='new').count(),
                'critical': alerts.filter(severity='critical').count(),
                'last_24h': alerts.filter(created_at__gte=last_24h).count(),
            },
            'telemetry': {
                'last_24h': Telemetry.objects.filter(
                    device__in=devices,
                    recorded_at__gte=last_24h
                ).count(),
            }
        })
    
    @action(detail=False, methods=['get'])
    def overview(self, request):
        """Получить общий обзор системы."""
        user = request.user
        
        if hasattr(user, 'role') and user.role.is_admin:
            devices = Device.objects.all()
        else:
            devices = Device.objects.filter(owner=user)
        
        # Группировка по типам
        device_types = devices.values('device_type__name').annotate(count=Count('id'))
        
        # Группировка по статусам
        status_dist = devices.values('status').annotate(count=Count('id'))
        
        return Response({
            'device_types': device_types,
            'status_distribution': status_dist,
        })


from django.db.models import Count
