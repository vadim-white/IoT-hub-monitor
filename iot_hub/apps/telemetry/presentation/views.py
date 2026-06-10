from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Min, Max, Count
from datetime import timedelta
import json
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
from iot_hub.apps.devices.models import Device, AlertThreshold
from iot_hub.apps.alerts.models import Alert
from iot_hub.apps.common.infrastructure.utils import export_telemetry_csv, export_telemetry_json


# ====== WEB VIEWS ======

@login_required(login_url='login')
def export_view(request):
    """Страница экспорта телеметрии."""
    is_admin = hasattr(request.user, 'role') and request.user.role.is_admin
    devices = Device.objects.all() if is_admin else Device.objects.filter(owner=request.user)
    devices = devices.select_related('device_type').order_by('name')

    # Диапазоны дат и количество записей по каждому устройству
    ranges_qs = (
        Telemetry.objects
        .filter(device__in=devices)
        .values('device_id')
        .annotate(min_date=Min('recorded_at'), max_date=Max('recorded_at'), count=Count('id'))
    )
    device_ranges = {
        str(r['device_id']): {
            'min_date': r['min_date'].strftime('%Y-%m-%d') if r['min_date'] else None,
            'max_date': r['max_date'].strftime('%Y-%m-%d') if r['max_date'] else None,
            'count': r['count'],
        }
        for r in ranges_qs
    }

    today = timezone.now().date()
    date_from_default = (today - timedelta(days=6)).isoformat()

    if request.method == 'POST':
        device_ids = request.POST.getlist('devices')
        date_from = request.POST.get('date_from') or None
        date_to = request.POST.get('date_to') or None
        fmt = request.POST.get('format', 'csv')

        # Не допускаем дату в будущем
        if date_to and date_to > today.isoformat():
            date_to = today.isoformat()

        qs = Telemetry.objects.filter(device__in=devices).order_by('device', 'recorded_at')

        if device_ids:
            qs = qs.filter(device_id__in=device_ids)
        if date_from:
            qs = qs.filter(recorded_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(recorded_at__date__lte=date_to)

        meta = {
            'period_from': date_from or '',
            'period_to': date_to or today.isoformat(),
        }

        if fmt == 'json':
            return export_telemetry_json(qs, filename='telemetry_export.json', meta=meta)
        return export_telemetry_csv(qs, filename='telemetry_export.csv')

    context = {
        'devices': devices,
        'device_ranges_json': json.dumps(device_ranges),
        'today': today.isoformat(),
        'date_from_default': date_from_default,
    }
    return render(request, 'telemetry/export.html', context)


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
    
    @action(detail=False, methods=['get'])
    def export(self, request):
        """Экспорт телеметрии через API. Query params: devices, date_from, date_to, format."""
        qs = self.get_queryset().order_by('device', 'recorded_at')

        device_ids = request.query_params.getlist('devices')
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        fmt = request.query_params.get('format', 'csv')

        if device_ids:
            qs = qs.filter(device_id__in=device_ids)
        if date_from:
            qs = qs.filter(recorded_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(recorded_at__date__lte=date_to)

        meta = {'period_from': date_from or '', 'period_to': date_to or ''}

        if fmt == 'json':
            return export_telemetry_json(qs, filename='telemetry_export.json', meta=meta)
        return export_telemetry_csv(qs, filename='telemetry_export.csv')

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

                    thresholds = AlertThreshold.objects.filter(
                        metric_id=metric_id, is_active=True
                    ).select_related('metric')
                    for threshold in thresholds:
                        if threshold.check_threshold(value):
                            Alert.objects.create(
                                device=device,
                                metric_id=metric_id,
                                threshold=threshold,
                                telemetry=telemetry,
                                severity=threshold.severity,
                                value=value,
                                message=(
                                    f"{threshold.metric.name}: {value} {metric_data.get('unit', '')} "
                                    f"(допустимо: {threshold.lower_bound if threshold.lower_bound is not None else '−∞'}"
                                    f" — {threshold.upper_bound if threshold.upper_bound is not None else '+∞'})"
                                ),
                                status='new',
                            )
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
