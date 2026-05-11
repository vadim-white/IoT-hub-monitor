from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from datetime import timedelta
from rest_framework import viewsets, status, filters, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from iot_hub.apps.telemetry.models import Telemetry, TelemetryBatch, TelemetryStatistics
from iot_hub.apps.telemetry.presentation.serializers import (
    TelemetrySerializer, TelemetryBatchSerializer, TelemetryStatisticsSerializer,
    TelemetryCreateSerializer
)
from iot_hub.apps.devices.models import Device


# ====== WEB VIEWS ======

@login_required(login_url='login')
def telemetry_view(request):
    """Просмотр телеметрических данных."""
    devices = Device.objects.filter(owner=request.user) if not hasattr(request.user, 'role') or not request.user.role.is_admin else Device.objects.all()
    
    device_id = request.GET.get('device_id')
    days = int(request.GET.get('days', 7))
    
    if device_id:
        device = devices.filter(id=device_id).first()
        if device:
            start_date = timezone.now() - timedelta(days=days)
            telemetry = Telemetry.objects.filter(
                device=device,
                recorded_at__gte=start_date
            ).select_related('metric').order_by('-recorded_at')
            
            context = {
                'device': device,
                'telemetry': telemetry[:100],
                'days': days,
                'devices': devices,
            }
            return render(request, 'telemetry/detail.html', context)
    
    context = {'devices': devices}
    return render(request, 'telemetry/list.html', context)


# ====== API VIEWS ======

class TelemetryViewSet(viewsets.ModelViewSet):
    """ViewSet для работы с историей телеметрии."""
    serializer_class = TelemetrySerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['device', 'metric', 'status']
    ordering_fields = ['recorded_at', 'value']
    ordering = ['-recorded_at']
    pagination_class = PageNumberPagination
    
    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'role') and user.role.is_admin:
            return Telemetry.objects.select_related('device', 'metric').all()
        return Telemetry.objects.filter(device__owner=user).select_related('device', 'metric')
    
    def get_serializer_class(self):
        if self.action == 'create':
            return TelemetryCreateSerializer
        return TelemetrySerializer
    
    @action(detail=False, methods=['get'])
    def by_device(self, request):
        """Получить телеметрию конкретного устройства."""
        device_id = request.query_params.get('device_id')
        limit = int(request.query_params.get('limit', 100))
        
        if not device_id:
            return Response({'error': 'device_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        telemetry = self.get_queryset().filter(device_id=device_id)[:limit]
        serializer = self.get_serializer(telemetry, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def by_metric(self, request):
        """Получить последние значения для всех метрик."""
        metrics = request.query_params.getlist('metric_ids')
        
        telemetry = Telemetry.objects.filter(metric_id__in=metrics).order_by(
            'metric', '-recorded_at'
        ).distinct('metric')
        
        serializer = self.get_serializer(telemetry, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def ingest(self, request):
        """Приём данных телеметрии от IoT-устройств."""
        device_id = request.data.get('device_id')
        metrics = request.data.get('metrics', [])
        
        if not device_id:
            return Response({'error': 'device_id is required'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        try:
            device = Device.objects.get(id=device_id)
        except Device.DoesNotExist:
            return Response({'error': 'Device not found'}, 
                          status=status.HTTP_404_NOT_FOUND)
        
        created_count = 0
        for metric_data in metrics:
            metric_id = metric_data.get('metric_id')
            value = metric_data.get('value')
            
            if metric_id and value is not None:
                try:
                    telemetry = Telemetry.objects.create(
                        device=device,
                        metric_id=metric_id,
                        value=value,
                        unit=metric_data.get('unit', ''),
                        status=metric_data.get('status', 'ok'),
                        raw_data=metric_data
                    )
                    created_count += 1
                except Exception as e:
                    pass
        
        # Обновляем время последнего подключения
        device.last_seen_at = timezone.now()
        device.status = 'active'
        device.save()
        
        return Response({
            'message': f'Created {created_count} telemetry records',
            'count': created_count
        }, status=status.HTTP_201_CREATED)


class TelemetryStatisticsViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet для статистики телеметрии."""
    serializer_class = TelemetryStatisticsSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'role') and user.role.is_admin:
            return TelemetryStatistics.objects.select_related('metric').all()
        return TelemetryStatistics.objects.filter(
            metric__device__owner=user
        ).select_related('metric')
