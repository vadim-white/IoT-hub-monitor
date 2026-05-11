from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from rest_framework import viewsets, status, filters, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from iot_hub.apps.devices.models import Device, DeviceType, DeviceMetric, AlertThreshold
from iot_hub.apps.devices.presentation.serializers import (
    DeviceSerializer, DeviceTypeSerializer, DeviceMetricSerializer, 
    AlertThresholdSerializer, DeviceCreateUpdateSerializer
)


# ====== WEB VIEWS ======

@login_required(login_url='login')
def devices_list(request):
    """Список всех устройств для пользователей."""
    if hasattr(request.user, 'role') and request.user.role.is_admin:
        devices = Device.objects.select_related('device_type', 'owner').all()
    else:
        devices = Device.objects.filter(owner=request.user).select_related('device_type')
    
    context = {
        'devices': devices,
        'total_devices': devices.count(),
        'active_devices': devices.filter(is_active=True).count(),
    }
    return render(request, 'devices/list.html', context)


@login_required(login_url='login')
def device_detail(request, device_id):
    """Детали устройства."""
    device = get_object_or_404(Device, id=device_id)
    
    # Проверка доступа
    if not (request.user == device.owner or 
            (hasattr(request.user, 'role') and request.user.role.is_admin)):
        return render(request, 'error.html', {'message': 'Access denied'}, status=403)
    
    metrics = device.metrics.select_related().prefetch_related('thresholds')
    
    context = {
        'device': device,
        'metrics': metrics,
        'thresholds': AlertThreshold.objects.filter(metric__device=device)
    }
    return render(request, 'devices/detail.html', context)


# ====== API VIEWS ======

class DeviceViewSet(viewsets.ModelViewSet):
    """ViewSet для управления IoT-устройствами."""
    serializer_class = DeviceSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'is_active', 'device_type']
    search_fields = ['name', 'serial_number', 'location_name']
    ordering_fields = ['created_at', 'last_seen_at', 'name']
    ordering = ['-last_seen_at']
    pagination_class = PageNumberPagination
    
    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'role') and user.role.is_admin:
            return Device.objects.select_related('device_type', 'owner').all()
        return Device.objects.filter(owner=user).select_related('device_type', 'owner')
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return DeviceCreateUpdateSerializer
        return DeviceSerializer
    
    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)
    
    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """Активировать устройство."""
        device = self.get_object()
        device.is_active = True
        device.status = 'active'
        device.save()
        return Response({'status': 'Device activated'})
    
    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        """Деактивировать устройство."""
        device = self.get_object()
        device.is_active = False
        device.status = 'inactive'
        device.save()
        return Response({'status': 'Device deactivated'})
    
    @action(detail=True, methods=['get'])
    def metrics(self, request, pk=None):
        """Получить метрики устройства."""
        device = self.get_object()
        metrics = device.metrics.all()
        serializer = DeviceMetricSerializer(metrics, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def online_count(self, request):
        """Получить количество онлайн устройств."""
        queryset = self.get_queryset()
        online = sum(1 for device in queryset if device.is_online)
        return Response({'online_devices': online, 'total_devices': queryset.count()})


class DeviceTypeViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet для типов устройств."""
    queryset = DeviceType.objects.all()
    serializer_class = DeviceTypeSerializer
    permission_classes = [permissions.IsAuthenticated]


class DeviceMetricViewSet(viewsets.ModelViewSet):
    """ViewSet для метрик устройств."""
    serializer_class = DeviceMetricSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        # Фильтр только для метрик устройств текущего пользователя
        user = self.request.user
        if hasattr(user, 'role') and user.role.is_admin:
            return DeviceMetric.objects.all()
        return DeviceMetric.objects.filter(device__owner=user)


class AlertThresholdViewSet(viewsets.ModelViewSet):
    """ViewSet для порогов алертов."""
    serializer_class = AlertThresholdSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'role') and user.role.is_admin:
            return AlertThreshold.objects.all()
        return AlertThreshold.objects.filter(metric__device__owner=user)
